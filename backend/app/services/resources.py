from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.orm import Session as DBSession

from app.models import (
    Analysis,
    AnalysisSource,
    AuditEvent,
    Job,
    Report,
    Source,
    StorageDeletion,
    User,
    now,
    uid,
)
from app.services import storage

LIMITATIONS = [
    "Interpretations describe captured document text, not real-world compliance or legal enforceability.",
    "AI semantic review can be wrong; source matching alone does not establish support.",
    "English text only. OCR and external legal research are not enabled.",
]
QUEUED_JOB_CLAIM_WINDOW = timedelta(minutes=15)


def owned(db, cls, ident, user, *, lock=False):
    row = (
        db.scalar(
            select(cls).where(cls.id == ident).with_for_update().execution_options(populate_existing=True)
        )
        if lock
        else db.get(cls, ident)
    )
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "Resource unavailable.")
    if isinstance(row, Source) and row.expires_at.replace(tzinfo=now().tzinfo) <= now():
        raise HTTPException(404, "Resource unavailable.")
    if isinstance(row, Analysis):
        sources = db.scalars(
            select(Source).join(AnalysisSource).where(AnalysisSource.analysis_id == row.id)
        ).all()
        if not sources or any(
            s.owner_id != user.id or s.expires_at.replace(tzinfo=now().tzinfo) <= now() for s in sources
        ):
            raise HTTPException(404, "Resource unavailable.")
    return row


def audit(db, user_id, action, object_id):
    db.add(AuditEvent(actor_id=user_id, action=action, object_id=object_id))


def quota(db, user):
    # Serialize per-account admission on PostgreSQL, including separate API replicas.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    _recover_stale_jobs(db, user)
    active = db.scalars(
        select(Job).where(Job.owner_id == user.id, Job.state.in_(["QUEUED", "PROCESSING"]))
    ).all()
    if len(active) >= (1 if user.is_guest else 2):
        raise HTTPException(429, "Finish or cancel an active job before starting another.")
    if user.is_guest:
        lifetime_jobs = len(db.scalars(select(Job.id).where(Job.owner_id == user.id)).all())
        if lifetime_jobs >= 10:
            raise HTTPException(429, "Guest quota reached. Create an account to continue.")


def _recover_stale_jobs(db, user):
    """Release persisted work that can no longer be active without deleting history."""
    from app.services.job_state import fail_processing

    processing = db.scalars(
        select(Job).where(
            Job.owner_id == user.id,
            Job.state == "PROCESSING",
            (Job.lease_until < now()) | Job.lease_until.is_(None),
        )
    ).all()
    recovered_processing = 0
    for job in processing:
        recovered_processing += fail_processing(
            db,
            job.id,
            job.lease_token,
            "WORKER_LEASE_EXPIRED: Worker interrupted; review checkpointed usage before retrying.",
            commit=False,
        )

    cutoff = now() - QUEUED_JOB_CLAIM_WINDOW
    queued = db.scalars(
        select(Job)
        .where(Job.owner_id == user.id, Job.state == "QUEUED", Job.created_at < cutoff)
        .with_for_update()
    ).all()
    for job in queued:
        job.state = "FAILED"
        job.stage = "FAILED"
        job.error = "Worker did not claim this job before the queue claim window expired."
        job.lease_token = None
        job.lease_until = None
        if job.source_id and job.kind in ("ingest", "capture"):
            source = db.get(Source, job.source_id)
            if source and source.status not in ("READY", "PARTIAL"):
                source.status = "FAILED"
    if recovered_processing or queued:
        db.commit()


def source_dict(source):
    return {
        "id": source.id,
        "source_id": source.id,
        "version": source.id,
        "original_name": source.details.get("display_name", source.original_name),
        "original_filename": source.original_name,
        "kind": source.kind,
        "sha256": source.sha256,
        "captured_at": source.captured_at.replace(tzinfo=now().tzinfo).isoformat(),
        "expires_at": source.expires_at.replace(tzinfo=now().tzinfo).isoformat(),
        "source_url": source.source_url,
        "status": source.status,
        **source.details,
    }


def create_source(db, user, data, name, kind="upload", metadata=None):
    # The public display name is never used as a filesystem path.
    name = Path(name.replace("\\", "/")).name[:255]
    ident = uid()
    key, sha = storage.write(data, ident)
    db.info.setdefault("new_private_objects", []).append(key)
    source = Source(
        id=ident,
        owner_id=user.id,
        original_name=name,
        kind=kind,
        object_key=key,
        sha256=sha,
        source_url=(metadata or {}).get("url"),
        expires_at=now() + timedelta(days=1 if user.is_guest else user.retention_days),
        details=metadata or {},
    )
    db.add(source)
    db.flush()
    job = Job(owner_id=user.id, source_id=ident, kind="ingest", payload={"source_id": ident})
    db.add(job)
    db.flush()
    audit(db, user.id, "source.created", ident)
    return source, job


@event.listens_for(DBSession, "after_rollback")
def compensate_storage_rollback(db):
    for key in db.info.pop("new_private_objects", []):
        storage.remove(key)


@event.listens_for(DBSession, "after_commit")
def committed_storage(db):
    db.info.pop("new_private_objects", None)


def flush_storage_deletions(db):
    """Durable outbox: delete bytes only after their source-deletion transaction committed."""
    for row in db.scalars(select(StorageDeletion).order_by(StorageDeletion.created_at).limit(100)).all():
        try:
            storage.remove(row.object_key)
        except OSError:
            row.attempts += 1
            row.last_error = "Private object deletion failed; worker will retry."
        else:
            db.delete(row)
    db.commit()


def delete_source(db, source):
    # Delete complete analyses referencing a source: never leave stale findings from a deleted scope.
    analysis_ids = db.scalars(
        select(AnalysisSource.analysis_id).where(AnalysisSource.source_id == source.id)
    ).all()
    keys = [source.object_key]
    for report in db.scalars(select(Report).where(Report.analysis_id.in_(analysis_ids))):
        keys.append(report.object_key)
        db.add(StorageDeletion(object_key=report.object_key))
    for analysis in db.scalars(select(Analysis).where(Analysis.id.in_(analysis_ids))):
        job = db.get(Job, analysis.job_id)
        if job:
            db.delete(job)
    audit(db, source.owner_id, "source.deleted", source.id)
    if not db.scalar(select(StorageDeletion).where(StorageDeletion.object_key == source.object_key)):
        db.add(StorageDeletion(object_key=source.object_key))
    db.delete(source)
    db.flush()
    return keys
