"""Durable DB worker. Run separately with `python -m app.worker`."""

import copy
import json
import logging
import signal
import threading
import time
import uuid
from datetime import timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Analysis,
    AnalysisSource,
    Chunk,
    EvidenceSpan,
    Finding,
    Job,
    ModelCall,
    RateBucket,
    Section,
    Session,
    Source,
    User,
    now,
    uid,
)
from app.runtime import worker_heartbeat
from app.services import storage
from app.services.resources import LIMITATIONS, delete_source, flush_storage_deletions


def save_finding(db, analysis_id, finding, sections, source_ids, unreadable=False):
    """One provenance check for incremental and final persistence. Caller owns transaction."""
    from app.services.verification import verify_quote

    value = copy.deepcopy(finding)
    if unreadable and value.get("support_status") == "SUPPORTED":
        value["support_status"] = "AMBIGUOUS"
        value.setdefault("verification", {}).update(
            support_status="AMBIGUOUS",
            rationale="Unextracted pages may contain material exceptions; review the complete source.",
        )
    checked = []
    for citation in value.get("citations", []):
        original = next((s for s in sections if s["id"] == citation.get("section_id")), None)
        section = db.get(Section, citation.get("section_id"))
        valid = verify_quote(citation, sections)
        if (
            not original
            or original.get("source_id") != citation.get("source_id")
            or not section
            or section.source_id not in source_ids
        ):
            valid["match_status"] = "INVALID"
        checked.append({**citation, **valid, "support_status": value.get("support_status", "AMBIGUOUS")})
    value["citations"] = checked
    if not checked or any(c["match_status"] not in ("EXACT", "NORMALIZED") for c in checked):
        value["support_status"] = "UNSUPPORTED"
        value["verification"] = {
            **value.get("verification", {}),
            "support_status": "UNSUPPORTED",
            "rationale": "Final deterministic source validation failed; no verified interpretation is claimed.",
        }
        for citation in checked:
            citation["support_status"] = "UNSUPPORTED"
    identity = [
        analysis_id,
        value.get("category"),
        " ".join(value.get("statement", "").casefold().split()),
        [
            (c.get("source_id"), c.get("section_id"), c.get("start"), c.get("end"), c.get("quote"))
            for c in checked
        ],
    ]
    ident = str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(identity, ensure_ascii=False)))
    value["id"] = value["finding_id"] = ident
    record = db.get(Finding, ident)
    if record and record.analysis_id != analysis_id:
        raise LeaseLost()
    if record:
        record.data = value
        db.execute(delete(EvidenceSpan).where(EvidenceSpan.finding_id == ident))
    else:
        record = Finding(id=ident, analysis_id=analysis_id, data=value)
        db.add(record)
    db.flush()
    for citation in checked:
        section = db.get(Section, citation.get("section_id"))
        if (
            citation["match_status"] in ("EXACT", "NORMALIZED")
            and section
            and section.source_id in source_ids
        ):
            db.add(
                EvidenceSpan(
                    finding_id=record.id,
                    source_id=section.source_id,
                    section_id=section.id,
                    quote=citation["quote"],
                    start=citation["start"],
                    end=citation["end"],
                    match_status=citation["match_status"],
                    locator=section.data.get("locator", {}),
                )
            )
    return value


class LeaseLost(Exception):
    pass


def claim():
    with SessionLocal() as db:
        # Fail interrupted work rather than silently repeating potentially billed model calls.
        stale_query = (
            select(Job)
            .where(Job.state == "PROCESSING", or_(Job.lease_until < now(), Job.lease_until.is_(None)))
            .limit(100)
        )
        if db.bind.dialect.name == "postgresql":
            stale_query = stale_query.with_for_update(skip_locked=True)
        for stale in db.scalars(stale_query).all():
            reason = (
                "Worker interrupted. Review provider usage before retrying; some calls may have completed."
            )
            from app.services.job_state import fail_processing

            fail_processing(db, stale.id, stale.lease_token, reason)
            if stale.kind in {"ingest", "capture"} and stale.source_id:
                source = db.get(Source, stale.source_id)
                if source:
                    source.status = "FAILED"
            logging.getLogger("veriora.worker").warning(
                "recovered stale job=%s kind=%s as %s", stale.id, stale.kind, stale.state
            )
        db.flush()
        db.commit()
        eligible = or_(
            Job.state == "QUEUED",
            (Job.state == "WAITING_RATE_LIMIT") & (Job.lease_until <= now()),
        )
        query = select(Job).where(eligible).order_by(Job.created_at).limit(1)
        if db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = db.scalar(query)
        if not job:
            return None
        token = uid()
        changed = db.execute(
            update(Job)
            .where(Job.id == job.id, eligible)
            .execution_options(synchronize_session=False)
            .values(
                state="PROCESSING",
                error=None,
                lease_token=token,
                lease_until=now() + timedelta(minutes=2),
                attempts=Job.attempts + 1,
            )
        )
        db.commit()
        return (job.id, token) if changed.rowcount else None


def progress(job_id, token, stage, completed=0, total=0, **details):
    with SessionLocal() as db:
        result = db.execute(
            update(Job)
            .where(Job.id == job_id, Job.lease_token == token, Job.state == "PROCESSING")
            .values(
                stage=stage,
                progress={"completed": completed, "total": total, **details},
                lease_until=now() + timedelta(minutes=2),
            )
        )
        db.commit()
        if not result.rowcount:
            raise LeaseLost()
        worker_heartbeat()
        logging.getLogger("veriora.worker").info(
            "job=%s stage=%s completed=%s total=%s", job_id, stage, completed, total
        )


def heartbeat(job_id, token, stop):
    while not stop.wait(15):
        try:
            with SessionLocal() as db:
                changed = db.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.lease_token == token, Job.state == "PROCESSING")
                    .values(lease_until=now() + timedelta(minutes=2))
                )
                db.commit()
                if not changed.rowcount:
                    return
                worker_heartbeat()
        except SQLAlchemyError as exc:
            logging.getLogger("veriora.worker").warning(
                "lease heartbeat failed error_type=%s", type(exc).__name__
            )


def ensure_active(db, job_id, token):
    job = db.scalar(
        select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True)
    )
    if not job or job.state != "PROCESSING" or job.lease_token != token:
        raise LeaseLost()
    return job


def ingest_source(job_id, token, source_id):
    from app.services.chunking import chunk_sections, count_tokens
    from app.services.ingest import extract

    progress(job_id, token, "VALIDATING")
    with SessionLocal() as db:
        source = db.get(Source, source_id)
        if not source or source.expires_at.replace(tzinfo=now().tzinfo) <= now():
            raise LeaseLost()
        ensure_active(db, job_id, token)
        source.status = "PROCESSING"
        db.commit()
        data, name = storage.read(source.object_key, source.sha256), source.original_name
    if not data or len(data) > settings().max_upload_bytes:
        raise ValueError("Document exceeds configured extraction limits.")
    progress(job_id, token, "PARSING")
    result = extract(data, name, max_bytes=settings().max_upload_bytes, max_pages=settings().max_pages)
    sections = result["sections"]
    for section in sections:
        section["id"] = source_id + ":" + str(section["ordinal"])
        section["source_id"] = source_id
    progress(job_id, token, "CHUNKING", len(sections), len(sections))
    tokens = sum(count_tokens(s["text"]) for s in sections)
    if tokens > settings().max_document_tokens:
        raise ValueError("Document exceeds the configured processing token limit.")
    chunks = chunk_sections(sections)
    with SessionLocal() as db:
        job = ensure_active(db, job_id, token)
        source = db.get(Source, source_id)
        db.execute(delete(Chunk).where(Chunk.source_id == source_id))
        db.execute(delete(Section).where(Section.source_id == source_id))
        for section in sections:
            db.add(Section(id=section["id"], source_id=source_id, ordinal=section["ordinal"], data=section))
        for index, chunk in enumerate(chunks):
            db.add(Chunk(source_id=source_id, ordinal=index, data=chunk))
        coverage = result["coverage"]
        source.status = (
            "PARTIAL" if coverage.get("pages_extracted", 0) < coverage.get("pages_total", 0) else "READY"
        )
        source.details = {
            **source.details,
            "coverage": coverage,
            "mime": result["mime"],
            "token_count": tokens,
            "chunks_total": len(chunks),
        }
        job.result = {"source_id": source_id, "coverage": coverage}
        job.state, job.stage, job.lease_token = "COMPLETED", "COMPLETED", None
        db.commit()


def process(job_id, token):
    from app.services.analysis import analyze
    from app.services.discovery import discover, safe_fetch

    with SessionLocal() as db:
        job = ensure_active(db, job_id, token)
        payload, kind, owner_id = job.payload, job.kind, job.owner_id
        user = db.get(User, owner_id)
        if not user or (
            user.is_guest and user.created_at.replace(tzinfo=now().tzinfo) <= now() - timedelta(days=1)
        ):
            raise ValueError("Session retention expired.")
    if kind == "ingest":
        ingest_source(job_id, token, payload["source_id"])
    elif kind == "discovery":
        progress(job_id, token, "FETCHING")
        result = discover(payload["url"])
        for candidate in result.get("candidates", []):
            if candidate.get("status") == "ACCESSIBLE":
                candidate["status"] = "AVAILABLE"
        with SessionLocal() as db:
            job = ensure_active(db, job_id, token)
            job.result, job.state, job.stage, job.lease_token = result, "COMPLETED", "COMPLETED", None
            db.commit()
    elif kind == "capture":
        with SessionLocal() as db:
            existing = db.get(Source, payload["source_id"])
            if existing and existing.owner_id == owner_id:
                ingest_source(job_id, token, existing.id)
                return
        progress(job_id, token, "FETCHING")
        fetched = safe_fetch(payload["url"])
        raw = fetched.pop("data")
        suffix = {"application/pdf": ".pdf", "text/plain": ".txt"}.get(fetched["mime"], ".html")
        key, sha = storage.write(raw, payload["source_id"])
        try:
            with SessionLocal() as db:
                job = ensure_active(db, job_id, token)
                user = db.get(User, owner_id)
                source = Source(
                    id=payload["source_id"],
                    owner_id=owner_id,
                    kind="url",
                    original_name="Captured policy" + suffix,
                    object_key=key,
                    sha256=sha,
                    source_url=fetched["url"],
                    expires_at=now() + timedelta(days=1 if user.is_guest else user.retention_days),
                    details={**fetched, "discovered_from": payload["discovered_from"]},
                )
                db.add(source)
                db.info.setdefault("new_private_objects", []).append(key)
                db.flush()
                job.source_id = source.id
                db.commit()
        except Exception:
            storage.remove(key)
            raise
        ingest_source(job_id, token, payload["source_id"])
    elif kind == "analysis":
        progress(job_id, token, "GENERATING")
        with SessionLocal() as db:
            analysis = db.scalar(select(Analysis).where(Analysis.job_id == job_id))
            source_ids = db.scalars(
                select(AnalysisSource.source_id).where(AnalysisSource.analysis_id == analysis.id)
            ).all()
            sources = db.scalars(select(Source).where(Source.id.in_(source_ids))).all()
            if not sources or any(
                s.owner_id != owner_id or s.expires_at.replace(tzinfo=now().tzinfo) <= now() for s in sources
            ):
                raise ValueError("Source scope expired or unavailable.")
            for source in sources:
                storage.read(source.object_key, source.sha256)
            sections = [
                s.data
                for s in db.scalars(
                    select(Section)
                    .where(Section.source_id.in_(source_ids))
                    .order_by(Section.source_id, Section.ordinal)
                )
            ]
            chunks = [
                c.data
                for c in db.scalars(
                    select(Chunk)
                    .where(Chunk.source_id.in_(source_ids))
                    .order_by(Chunk.source_id, Chunk.ordinal)
                )
            ]
            source_warnings = [
                w
                for s in db.scalars(select(Source).where(Source.id.in_(source_ids)))
                for w in s.details.get("coverage", {}).get("warnings", [])
            ]
        from app.services.provider_policy import providers_for

        with SessionLocal() as policy_db:
            owner = policy_db.get(User, job.owner_id)
            providers = providers_for(owner, payload, SessionLocal)
            for config in providers:
                config["budget"]["deadline"] = time.monotonic() + settings().analysis_timeout_seconds
        from app.services.checkpoints import RequestCheckpoints

        checkpoints = RequestCheckpoints(SessionLocal, job_id, token)
        snapshot_unreadable = any(
            s.details.get("coverage", {}).get("pages_extracted", 0)
            < s.details.get("coverage", {}).get("pages_total", 0)
            for s in sources
        )

        def retain_finding(finding):
            with SessionLocal() as snapshot_db:
                active = ensure_active(snapshot_db, job_id, token)
                parent = snapshot_db.scalar(select(Analysis).where(Analysis.job_id == job_id))
                if not parent or parent.owner_id != active.owner_id:
                    raise LeaseLost()
                save_finding(snapshot_db, parent.id, finding, sections, source_ids, snapshot_unreadable)
                parent.coverage = {
                    "sections_total": len(sections),
                    "sections_processed": 0,
                    "chunks_total": len(chunks),
                    "chunks_processed": 0,
                    "warnings": ["Incremental findings retained; source processing is not complete."],
                }
                snapshot_db.commit()

        for provider in providers:
            provider["job_id"] = job_id
            provider["analysis_id"] = analysis.id
            provider["checkpoint"] = checkpoints
            provider["on_finding"] = retain_finding
            provider["on_index_progress"] = lambda event: progress(
                job_id,
                token,
                "AI_CONTEXT_INDEXING",
                event["windows_reviewed"],
                event["windows_total"],
                source_audit=event,
            )
            provider["on_attempt"] = lambda event: progress(
                job_id, token, "AI_" + event["role"].upper(), **event
            )
        result = analyze(
            chunks,
            sections,
            providers,
            lambda stage, done, total: progress(job_id, token, stage, done, total),
        )
        progress(job_id, token, "AGGREGATING")
        with SessionLocal() as db:
            job = ensure_active(db, job_id, token)
            analysis = db.scalar(select(Analysis).where(Analysis.job_id == job_id))
            db.execute(delete(Finding).where(Finding.analysis_id == analysis.id))
            for call in result.get("model_calls", []):
                db.add(ModelCall(job_id=job_id, data=call))
            analysis.coverage = {
                **result["coverage"],
                "warnings": source_warnings + result.get("warnings", []),
            }
            analysis.limitations = list(
                dict.fromkeys(LIMITATIONS + result.get("limitations", []) + result.get("warnings", []))
            )
            coverage = result["coverage"]
            failed = coverage.get("chunks_processed", 0) < coverage.get("chunks_total", len(chunks))
            unreadable = any(
                s.details.get("coverage", {}).get("pages_extracted", 0)
                < s.details.get("coverage", {}).get("pages_total", 0)
                for s in db.scalars(select(Source).where(Source.id.in_(source_ids)))
            )
            for index, finding in enumerate(result["findings"]):
                result["findings"][index] = save_finding(
                    db, analysis.id, finding, sections, source_ids, unreadable
                )
            incomplete_verification = any(
                f.get("verification", {}).get("error_code")
                or any(c.get("match_status") == "INVALID" for c in f.get("citations", []))
                for f in result["findings"]
            )
            job.state = (
                "PARTIAL_COMPLETION"
                if failed or unreadable or incomplete_verification or result.get("warnings")
                else "COMPLETED"
            )
            job.stage, job.lease_token = job.state, None
            job.result = {"analysis_id": analysis.id, "findings_count": len(result["findings"])}
            db.commit()
    else:
        raise ValueError("Unsupported processing job.")


def run_once():
    claimed = claim()
    if not claimed:
        return False
    job_id, token = claimed
    logging.getLogger("veriora.worker").info("claimed job=%s", job_id)
    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(job_id, token, stop), daemon=True)
    thread.start()
    watchdog = None
    with SessionLocal() as db:
        running = db.get(Job, job_id)
        if running and running.kind == "analysis":
            running.result = {
                **running.result,
                "processing_started_at": now().isoformat(),
                "analysis_timeout_seconds": settings().analysis_timeout_seconds,
            }
            db.commit()

            def expire():
                from app.services.job_state import fail_processing

                try:
                    with SessionLocal() as expired_db:
                        if fail_processing(
                            expired_db,
                            job_id,
                            token,
                            "ANALYSIS_DEADLINE_EXCEEDED: Processing time limit reached. Completed responses are checkpointed; review partial results or retry safely.",
                        ):
                            logging.getLogger("veriora.worker").warning(
                                "job=%s terminal_reason=ANALYSIS_DEADLINE_EXCEEDED", job_id
                            )
                except SQLAlchemyError as exc:
                    logging.getLogger("veriora.worker").warning(
                        "deadline persistence failed error_type=%s", type(exc).__name__
                    )

            watchdog = threading.Timer(settings().analysis_timeout_seconds + 5, expire)
            watchdog.daemon = True
            watchdog.start()
    try:
        process(job_id, token)
    except LeaseLost:
        pass
    except Exception as exc:  # noqa: BLE001 - worker boundary persists redacted failure, never success
        from app.providers.base import ProviderError
        from app.services.discovery import DiscoveryError
        from app.services.ingest import ExtractionError

        safe = (
            str(exc)
            if isinstance(exc, (ExtractionError, DiscoveryError))
            else "Processing failed. Check configuration and retry."
        )
        if isinstance(exc, ProviderError):
            codes = sorted({c.get("outcome", "") for c in exc.model_calls if c.get("outcome") != "SUCCESS"})
            safe = (
                "AI provider failed: "
                + exc.code
                + ". "
                + ", ".join(codes)
                + ". Processing is incomplete; retained findings preserve their recorded verification status."
            )
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job and job.lease_token == token:
                if job.source_id and job.kind in ("ingest", "capture"):
                    source = db.get(Source, job.source_id)
                    if source:
                        source.status = "FAILED"
                for call in getattr(exc, "model_calls", []):
                    db.add(ModelCall(job_id=job_id, data=call))
                from app.services.job_state import fail_processing
                from app.services.rate_limit_recovery import pause

                if not (isinstance(exc, ProviderError) and pause(db, job_id, token, exc)):
                    recovery_reason = (job.result or {}).get("rate_limit_recovery", {}).get("stop_reason")
                    if recovery_reason:
                        safe += " Automatic recovery stopped: " + recovery_reason + "."
                    fail_processing(db, job_id, token, safe)
                logging.getLogger("veriora.worker").warning(
                    "job=%s state=%s error_type=%s", job_id, job.state, type(exc).__name__
                )
    finally:
        if watchdog is not None:
            watchdog.cancel()
        stop.set()
        thread.join(timeout=2)
    worker_heartbeat()
    with SessionLocal() as db:
        finished = db.get(Job, job_id)
        logging.getLogger("veriora.worker").info(
            "finished job=%s state=%s stage=%s",
            job_id,
            finished.state if finished else "DELETED",
            finished.stage if finished else "DELETED",
        )
    return True


def cleanup():
    from app.models import AuthToken, OAuthAttempt, PendingRegistration

    with SessionLocal() as db:
        for model in (PendingRegistration, OAuthAttempt, AuthToken):
            db.execute(delete(model).where(model.expires_at <= now()))
        for source in db.scalars(select(Source).where(Source.expires_at <= now())).all():
            delete_source(db, source)
        db.execute(delete(Session).where(Session.expires_at <= now()))
        db.execute(delete(RateBucket).where(RateBucket.expires_at <= now()))
        # Guest identities and discovery metadata expire after 24 hours too.
        for user in db.scalars(
            select(User).where(User.is_guest.is_(True), User.created_at < now() - timedelta(days=1))
        ).all():
            for source in db.scalars(select(Source).where(Source.owner_id == user.id)).all():
                delete_source(db, source)
            db.delete(user)
        db.commit()
        # Unknown files may belong to another database or preserved deployment. Never sweep them.
        flush_storage_deletions(db)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log = logging.getLogger("veriora.worker")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    log.info("consumer started; concurrency=1; durable leases enabled")
    last_cleanup = 0.0
    backoff = 1
    while not stop.is_set():
        try:
            if time.monotonic() - last_cleanup > 60:
                cleanup()
                last_cleanup = time.monotonic()
            if not run_once():
                worker_heartbeat()
                stop.wait(2)
            backoff = 1
        except SQLAlchemyError as exc:
            log.warning(
                "queue database unavailable error_type=%s retry_seconds=%s", type(exc).__name__, backoff
            )
            stop.wait(backoff)
            backoff = min(backoff * 2, 30)
    log.info("consumer stopped; unfinished leases will be recovered without automatic AI replay")


if __name__ == "__main__":
    main()
