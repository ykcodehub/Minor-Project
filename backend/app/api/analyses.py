import io
import json
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from sqlalchemy import String, cast, func, select

from app.config import settings
from app.models import (
    Analysis,
    AnalysisCheckpoint,
    AnalysisSource,
    Finding,
    Job,
    LocalizedAnalysis,
    ModelCall,
    Question,
    Report,
    Section,
    Source,
    now,
    uid,
)
from app.schemas import (
    AnalysisCreated,
    AnalysisInput,
    AnalysisResponse,
    ConversationResponse,
    FindingResponse,
    JobResponse,
    Language,
    QuestionInput,
    QuestionResponse,
    ReportResponse,
    RetryInput,
)
from app.security import CurrentUser, Db, throttle
from app.services.resources import LIMITATIONS, audit, owned, quota, source_dict

router = APIRouter()


def analysis_sources(db, analysis):
    return db.scalars(
        select(Source).join(AnalysisSource).where(AnalysisSource.analysis_id == analysis.id)
    ).all()


def finding_dict(row):
    return {**row.data, "id": row.id, "finding_id": row.id}


def call_dict(row):
    return {
        **row.data,
        "created_at": row.created_at.replace(tzinfo=now().tzinfo).isoformat() if row.created_at else None,
    }


@router.post("/analyses", status_code=202, response_model=AnalysisCreated)
def create_analysis(
    data: AnalysisInput,
    db: Db,
    user: CurrentUser,
    idempotency_key: str | None = Header(default=None, max_length=160),
):
    from app.providers.base import ProviderError
    from app.services.provider_policy import names_for, providers_for

    if user.authorized_providers is not None:
        names = names_for(user, data.model_dump())
        if not names:
            raise HTTPException(403, "Authorize AI providers in Settings before analysis.")
        data = data.model_copy(
            update={"provider": names[0], "fallback_providers": names[1:], "consent": True}
        )
    if idempotency_key:
        previous = db.scalar(
            select(Job).where(Job.owner_id == user.id, Job.idempotency_key == idempotency_key)
        )
        if previous:
            if previous.kind != "analysis" or previous.payload != data.model_dump():
                raise HTTPException(409, "Idempotency key was already used for a different request.")
            analysis = db.scalar(select(Analysis).where(Analysis.job_id == previous.id))
            return {"analysis_id": analysis.id, "job_id": previous.id}
    if data.privacy_mode != "external" or not data.consent:
        raise HTTPException(
            422,
            "External AI requires your explicit provider consent. Confidential processing is unavailable.",
        )
    if not user.is_guest and not user.verified_at:
        raise HTTPException(403, "Verify your email before using external AI.")
    try:
        providers_for(user, data.model_dump())
    except ProviderError as exc:
        raise HTTPException(503, exc.code) from None
    quota(db, user)
    sources = [owned(db, Source, sid, user) for sid in dict.fromkeys(data.source_ids)]
    if any(source.status not in ("READY", "PARTIAL") for source in sources):
        raise HTTPException(409, "Wait for source extraction to finish before starting analysis.")
    if sum(s.details.get("token_count", 0) for s in sources) > settings().max_document_tokens:
        raise HTTPException(422, "The selected documents exceed the configured token budget.")
    job = Job(owner_id=user.id, kind="analysis", payload=data.model_dump(), idempotency_key=idempotency_key)
    db.add(job)
    db.flush()
    analysis = Analysis(owner_id=user.id, job_id=job.id, limitations=LIMITATIONS)
    db.add(analysis)
    db.flush()
    for source in sources:
        db.add(AnalysisSource(analysis_id=analysis.id, source_id=source.id))
    audit(db, user.id, "analysis.consented", analysis.id)
    db.commit()
    return {"analysis_id": analysis.id, "job_id": job.id}


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: str, db: Db, user: CurrentUser):
    analysis = owned(db, Analysis, analysis_id, user)
    job = db.get(Job, analysis.job_id)
    sources = analysis_sources(db, analysis)
    from app.services.overview import build_overview

    overview = build_overview(
        [
            s.data
            for s in db.scalars(
                select(Section)
                .where(Section.source_id.in_([s.id for s in sources]))
                .order_by(Section.source_id, Section.ordinal)
            )
        ],
        [f.data for f in db.scalars(select(Finding).where(Finding.analysis_id == analysis.id))],
        analysis.coverage,
        job.state,
    )
    return {
        "id": analysis.id,
        "analysis_id": analysis.id,
        "job_id": job.id,
        "status": job.state,
        "created_at": analysis.created_at.replace(tzinfo=now().tzinfo).isoformat(),
        "source_ids": [s.id for s in sources],
        "sources": [source_dict(s) for s in sources],
        "coverage": analysis.coverage,
        "limitations": analysis.limitations,
        "overview": overview,
        "findings_count": len(db.scalars(select(Finding.id).where(Finding.analysis_id == analysis.id)).all()),
        "model_calls": [
            call_dict(c) for c in db.scalars(select(ModelCall).where(ModelCall.job_id == job.id))
        ],
    }


@router.get("/analyses/{analysis_id}/findings", response_model=list[FindingResponse])
def get_findings(
    analysis_id: str,
    db: Db,
    user: CurrentUser,
    category: str | None = None,
    status: str | None = None,
    q: str = "",
    offset: int = 0,
    limit: int = 200,
    source_id: str | None = None,
    response: Response = None,
):
    owned(db, Analysis, analysis_id, user)
    if offset < 0 or not 1 <= limit <= 200:
        raise HTTPException(422, "Invalid pagination.")
    query = select(Finding).where(Finding.analysis_id == analysis_id)
    if category:
        query = query.where(Finding.data["category"].as_string().in_(category.split(",")))
    if status:
        query = query.where(Finding.data["support_status"].as_string() == status)
    if q:
        query = query.where(
            cast(Finding.data, String).ilike(
                "%" + q.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"
            )
        )
    if source_id:
        from app.models import EvidenceSpan

        query = query.where(
            Finding.id.in_(select(EvidenceSpan.finding_id).where(EvidenceSpan.source_id == source_id))
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
    return [finding_dict(f) for f in db.scalars(query.order_by(Finding.id).offset(offset).limit(limit))]


@router.get("/analyses/{analysis_id}/findings/{finding_id}", response_model=FindingResponse)
def get_finding(analysis_id: str, finding_id: str, db: Db, user: CurrentUser):
    owned(db, Analysis, analysis_id, user)
    row = db.get(Finding, finding_id)
    if not row or row.analysis_id != analysis_id:
        raise HTTPException(404, "Finding unavailable.")
    return finding_dict(row)


@router.post("/analyses/{analysis_id}/questions", response_model=QuestionResponse)
def ask_question(analysis_id: str, data: QuestionInput, db: Db, user: CurrentUser):
    from app.providers.base import ProviderError
    from app.services.analysis import ask

    throttle(db, "question:" + user.id, 20, 3600)
    analysis = owned(db, Analysis, analysis_id, user)
    job = db.get(Job, analysis.job_id)
    if job.state not in ("COMPLETED", "PARTIAL_COMPLETION"):
        raise HTTPException(409, "Wait for analysis results before asking questions.")
    from app.services.provider_policy import providers_for

    try:
        providers = providers_for(user, job.payload)
    except ProviderError as exc:
        raise HTTPException(403 if exc.code == "PROVIDER_PERMISSION_REVOKED" else 503, exc.code) from None
    sources = analysis_sources(db, analysis)
    sections = [
        s.data for s in db.scalars(select(Section).where(Section.source_id.in_([s.id for s in sources])))
    ]
    findings = [
        finding_dict(f) for f in db.scalars(select(Finding).where(Finding.analysis_id == analysis.id))
    ]
    try:
        from app.services.localization import retrieval_question
        from app.services.retrieval import retrieve_chunks

        search_question, retrieval_calls = retrieval_question(data.question, providers)
        for call in retrieval_calls:
            db.add(ModelCall(job_id=job.id, data=call))
        chunks = retrieve_chunks(db, [s.id for s in sources], search_question, owner_id=user.id)
        result = ask(
            data.question,
            findings,
            sections,
            providers,
            retrieved_chunks=chunks,
            language=data.language or user.language,
        )
        result["language"] = data.language or user.language
    except ProviderError as exc:
        for call in exc.model_calls:
            db.add(ModelCall(job_id=job.id, data=call))
        db.commit()
        raise HTTPException(
            503, "The AI provider could not answer this question. Please retry later."
        ) from None
    for call in result.pop("model_calls", []):
        db.add(ModelCall(job_id=job.id, data=call))
    if not user.is_guest:
        db.add(Question(analysis_id=analysis.id, question=data.question, answer=result))
    db.commit()
    return result


@router.get("/analyses/{analysis_id}/questions", response_model=list[ConversationResponse])
def question_history(analysis_id: str, db: Db, user: CurrentUser):
    owned(db, Analysis, analysis_id, user)
    return [
        {
            "question": q.question,
            **q.answer,
            "created_at": q.created_at.replace(tzinfo=now().tzinfo).isoformat(),
        }
        for q in db.scalars(
            select(Question).where(Question.analysis_id == analysis_id).order_by(Question.created_at)
        )
    ]


@router.get("/analyses/{analysis_id}/exports")
def export_analysis(
    analysis_id: str,
    db: Db,
    user: CurrentUser,
    format: Literal["json", "pdf"] = "json",
    language: Language = "en",
):
    if user.is_guest:
        raise HTTPException(403, "Create an account for durable evidence exports.")
    analysis = owned(db, Analysis, analysis_id, user)
    job = db.get(Job, analysis.job_id)
    if job.state not in ("COMPLETED", "PARTIAL_COMPLETION"):
        raise HTTPException(409, "A report requires completed or explicitly partial analysis results.")
    sources = analysis_sources(db, analysis)
    findings = [
        finding_dict(f) for f in db.scalars(select(Finding).where(Finding.analysis_id == analysis.id))
    ]
    from app.services import storage

    for source in sources:
        storage.read(source.object_key, source.sha256)
    manifest = {
        "schema_version": "2.0",
        "analysis_id": analysis.id,
        "status": job.state,
        "created_at": analysis.created_at.replace(tzinfo=now().tzinfo).isoformat(),
        "sources": [source_dict(s) for s in sources],
        "coverage": analysis.coverage,
        "findings": findings,
        "limitations": analysis.limitations,
        "model_calls": [
            call_dict(c) for c in db.scalars(select(ModelCall).where(ModelCall.job_id == analysis.job_id))
        ],
    }

    if language != "en":
        from app.services.localization import fingerprint

        saved = db.scalar(
            select(LocalizedAnalysis).where(
                LocalizedAnalysis.analysis_id == analysis.id,
                LocalizedAnalysis.language == language,
                LocalizedAnalysis.fingerprint == fingerprint(sorted(findings, key=lambda f: f["id"])),
            )
        )
        if findings and not saved:
            raise HTTPException(409, "Prepare verified translations before exporting in this language.")
        if saved:
            manifest["findings"] = [
                {
                    **f,
                    "original_explanation": {
                        "statement": f["statement"],
                        "rationale": f.get("rationale", ""),
                        "qualifications": f.get("qualifications", []),
                    },
                    **saved.data.get(f["id"], {}),
                }
                for f in findings
            ]
    manifest["language"] = language

    def save_report(payload):
        ident = uid()
        key, digest = storage.write(payload, ident)
        db.info.setdefault("new_private_objects", []).append(key)
        db.add(
            Report(
                id=ident,
                owner_id=user.id,
                analysis_id=analysis.id,
                object_key=key,
                format=format,
                sha256=digest,
            )
        )
        audit(db, user.id, "report.exported", analysis.id)
        db.commit()
        return ident

    if format == "json":
        payload = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        report_id = save_report(payload)
        return Response(
            payload,
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="veriora-evidence.json"',
                "X-Report-ID": report_id,
            },
        )
    import pymupdf

    from app.services.reports import report_html

    output = io.BytesIO()
    writer = pymupdf.DocumentWriter(output)
    story = pymupdf.Story(
        html=report_html(manifest),
        user_css="""
        body{font-family:sans-serif;font-size:10pt;color:#17212B;line-height:1.5;}
        h1{color:#176B66;font-size:28pt;} h2{color:#176B66;font-size:16pt;margin-top:24pt;}
        h3{font-size:12pt;margin-top:18pt;} blockquote{border-left:3px solid #176B66;padding:10pt;background:#E9F4F1;}
        .eyebrow{font-size:9pt;color:#536271;} .hash{font-family:monospace;font-size:8pt;}
    """,
    )
    more = True
    while more:
        device = writer.begin_page(pymupdf.Rect(0, 0, 595, 842))
        more, _ = story.place(pymupdf.Rect(40, 40, 555, 802))
        story.draw(device)
        writer.end_page()
    writer.close()
    payload = output.getvalue()
    report_id = save_report(payload)
    return Response(
        payload,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="veriora-report.pdf"',
            "X-Report-ID": report_id,
        },
    )


@router.get("/exports/{report_id}")
def stored_report(report_id: str, db: Db, user: CurrentUser):
    from app.services import storage

    report = owned(db, Report, report_id, user)
    owned(db, Analysis, report.analysis_id, user)
    payload = storage.read(report.object_key, report.sha256)
    return Response(
        payload,
        media_type="application/pdf" if report.format == "pdf" else "application/json",
        headers={"Content-Disposition": f'attachment; filename="veriora-report.{report.format}"'},
    )


@router.get("/analyses/{analysis_id}/reports", response_model=list[ReportResponse])
def report_history(analysis_id: str, db: Db, user: CurrentUser):
    owned(db, Analysis, analysis_id, user)
    return [
        {
            "id": r.id,
            "format": r.format,
            "sha256": r.sha256,
            "created_at": r.created_at.replace(tzinfo=now().tzinfo).isoformat(),
        }
        for r in db.scalars(
            select(Report)
            .where(Report.analysis_id == analysis_id)
            .order_by(Report.created_at.desc())
            .limit(100)
        )
    ]


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Db, user: CurrentUser):
    job = owned(db, Job, job_id, user)
    return {
        "id": job.id,
        "job_id": job.id,
        "state": job.state,
        "stage": job.stage,
        "progress": job.progress,
        "error": job.error,
        "attempts": job.attempts,
        "uncertain_ai_requests": db.scalar(
            select(func.count())
            .select_from(AnalysisCheckpoint)
            .where(AnalysisCheckpoint.job_id == job.id, AnalysisCheckpoint.state == "RUNNING")
        ),
        "result": job.result,
    }


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Db, user: CurrentUser):
    job = owned(db, Job, job_id, user, lock=True)
    if job.state not in ("QUEUED", "PROCESSING"):
        raise HTTPException(409, "This job has already finished.")
    job.state = "CANCELLED"
    job.stage = "CANCELLED"
    job.lease_token = None
    if job.source_id and job.kind in ("ingest", "capture"):
        source = db.get(Source, job.source_id)
        if source and source.status not in ("READY", "PARTIAL"):
            source.status = "CANCELLED"
    db.commit()
    return {"state": job.state}


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, db: Db, user: CurrentUser, data: RetryInput | None = None):
    quota(db, user)
    job = owned(db, Job, job_id, user, lock=True)
    if job.state not in ("FAILED", "CANCELLED", "PARTIAL_COMPLETION"):
        raise HTTPException(409, "This job cannot be retried in its current state.")
    if job.attempts >= 3:
        raise HTTPException(409, "Retry limit reached. Create a new analysis after resolving the error.")
    if job.kind == "analysis":
        from app.providers.base import ProviderError
        from app.services.provider_policy import providers_for

        try:
            providers_for(user, job.payload)
        except ProviderError as exc:
            raise HTTPException(403 if exc.code == "PROVIDER_PERMISSION_REVOKED" else 503, exc.code) from None
    uncertain = db.scalars(
        select(AnalysisCheckpoint).where(
            AnalysisCheckpoint.job_id == job.id, AnalysisCheckpoint.state == "RUNNING"
        )
    ).all()
    if uncertain and not (data and data.acknowledge_uncertain_calls):
        raise HTTPException(
            409,
            "An interrupted AI request may already have been billed. Explicit acknowledgment is required before retrying it.",
        )
    for record in uncertain:
        record.state = "ABANDONED"
    job.state, job.stage, job.error = "QUEUED", "RECEIVED", None
    job.lease_token = None
    job.lease_until = None
    if job.source_id and job.kind in ("ingest", "capture"):
        source = db.get(Source, job.source_id)
        if source:
            source.status = "QUEUED"
    db.commit()
    return {"job_id": job.id, "state": job.state}


@router.get("/analyses/{analysis_id}/summary")
def analysis_summary(analysis_id: str, db: Db, user: CurrentUser, language: Language = "en"):
    from app.services.localization import fingerprint
    from app.services.summary import suggested_questions, summarize

    analysis = owned(db, Analysis, analysis_id, user)
    job = db.get(Job, analysis.job_id)
    findings = [
        finding_dict(f)
        for f in db.scalars(select(Finding).where(Finding.analysis_id == analysis.id).order_by(Finding.id))
    ]
    sections = [
        s.data
        for s in db.scalars(
            select(Section).where(Section.source_id.in_([s.id for s in analysis_sources(db, analysis)]))
        )
    ]
    summary = summarize(findings, sections, analysis.coverage, job.state)
    summary["failure_codes"] = sorted(
        {
            ("PROVIDER_CONTEXT_LIMIT" if c.data.get("http_status") == 413 else c.data.get("outcome"))
            for c in db.scalars(select(ModelCall).where(ModelCall.job_id == job.id))
            if c.data.get("outcome") and c.data.get("outcome") != "SUCCESS"
        }
    )
    translations = {}
    if language != "en":
        saved = db.scalar(
            select(LocalizedAnalysis).where(
                LocalizedAnalysis.analysis_id == analysis.id,
                LocalizedAnalysis.language == language,
                LocalizedAnalysis.fingerprint == fingerprint(findings),
            )
        )
        if saved:
            translations = saved.data
    # GET never makes a billable provider request. Client explicitly prepares a translation.
    return {
        "summary": summary,
        "language": language,
        "translations": translations,
        "translation_ready": language == "en" or bool(translations) or not findings,
        "fingerprint": fingerprint(findings),
        "suggested_questions": suggested_questions(findings, language),
    }


@router.post("/analyses/{analysis_id}/translations")
def translate_analysis(analysis_id: str, db: Db, user: CurrentUser, language: Language):
    from sqlalchemy.exc import IntegrityError

    from app.providers.base import ProviderError
    from app.services.localization import fingerprint, localize

    analysis = owned(db, Analysis, analysis_id, user)
    job = db.get(Job, analysis.job_id)
    if job.state not in ("COMPLETED", "PARTIAL_COMPLETION"):
        raise HTTPException(409, "Wait for analysis results before translating.")
    findings = [
        finding_dict(f)
        for f in db.scalars(select(Finding).where(Finding.analysis_id == analysis.id).order_by(Finding.id))
    ]
    stamp = fingerprint(findings)
    saved = db.scalar(
        select(LocalizedAnalysis).where(
            LocalizedAnalysis.analysis_id == analysis.id,
            LocalizedAnalysis.language == language,
            LocalizedAnalysis.fingerprint == stamp,
        )
    )
    if language == "en" or saved or not findings:
        return {"ready": True}
    throttle(db, "translation:" + user.id, 10, 3600)
    # Serialize translations for this analysis to avoid duplicate billable requests.
    analysis = owned(db, Analysis, analysis_id, user, lock=True)
    saved = db.scalar(
        select(LocalizedAnalysis).where(
            LocalizedAnalysis.analysis_id == analysis.id,
            LocalizedAnalysis.language == language,
            LocalizedAnalysis.fingerprint == stamp,
        )
    )
    if saved:
        return {"ready": True}
    from app.services.provider_policy import providers_for

    try:
        providers = providers_for(user, job.payload)
    except ProviderError as exc:
        raise HTTPException(403 if exc.code == "PROVIDER_PERMISSION_REVOKED" else 503, exc.code) from None
    try:
        translated, calls = localize(findings, language, providers)
    except ProviderError as exc:
        for call in exc.model_calls:
            db.add(ModelCall(job_id=job.id, data=call))
        db.commit()
        raise HTTPException(
            503, "Translation could not be verified. Original analysis remains available."
        ) from None
    for call in calls:
        db.add(ModelCall(job_id=job.id, data=call))
    db.add(LocalizedAnalysis(analysis_id=analysis.id, language=language, fingerprint=stamp, data=translated))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"ready": True}
