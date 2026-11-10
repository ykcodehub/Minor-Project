import hashlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select

from app.config import settings
from app.models import Analysis, AnalysisSource, Job, Section, Source, StorageDeletion, now, uid
from app.schemas import (
    DiscoveryInput,
    DiscoveryResponse,
    JobCreated,
    RenameInput,
    SectionResponse,
    SourceCreated,
    SourceResponse,
    TextInput,
    URLInput,
)
from app.security import CurrentUser, Db, throttle
from app.services import storage
from app.services.resources import (
    create_source,
    delete_source,
    flush_storage_deletions,
    owned,
    quota,
    source_dict,
)

router = APIRouter()


def accepted(source, job):
    return {"source_id": source.id, "job_id": job.id}


def existing_ingest(db, user, key, data, name):
    if not key:
        return None
    previous = db.scalar(select(Job).where(Job.owner_id == user.id, Job.idempotency_key == key))
    if not previous:
        return None
    if (
        previous.kind != "ingest"
        or previous.payload.get("input_hash") != hashlib.sha256(data).hexdigest()
        or previous.payload.get("input_name") != name
    ):
        raise HTTPException(409, "Idempotency key was already used for a different request.")
    return accepted(owned(db, Source, previous.source_id, user), previous)


def ingestion_key(job, key, raw, name):
    job.idempotency_key = key
    job.payload = {**job.payload, "input_hash": hashlib.sha256(raw).hexdigest(), "input_name": name}


@router.get("/sources", response_model=list[SourceResponse])
def sources(
    db: Db,
    user: CurrentUser,
    response: Response,
    offset: int = 0,
    limit: int = 100,
    q: str = "",
    status: str | None = None,
    sort: str = "captured_desc",
):
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "Invalid pagination.")
    query = select(Source).where(Source.owner_id == user.id, Source.expires_at > now())
    display_name = func.coalesce(Source.details["display_name"].as_string(), Source.original_name)
    if q:
        query = query.where(
            display_name.ilike("%" + q.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\")
        )
    if status:
        query = query.where(Source.status == status)
    order = {
        "captured_desc": Source.captured_at.desc(),
        "captured_asc": Source.captured_at.asc(),
        "name_asc": display_name.asc(),
        "name_desc": display_name.desc(),
    }
    if sort not in order:
        raise HTTPException(422, "Invalid source sort order.")
    response.headers["X-Total-Count"] = str(db.scalar(select(func.count()).select_from(query.subquery())))
    rows = db.scalars(query.order_by(order[sort], Source.id).offset(offset).limit(limit))
    result = []
    for source in rows:
        item = source_dict(source)
        item["analysis_id"] = db.scalar(
            select(AnalysisSource.analysis_id)
            .join(Analysis)
            .where(AnalysisSource.source_id == source.id)
            .order_by(Analysis.created_at.desc())
            .limit(1)
        )
        if item["analysis_id"]:
            item["analysis_status"] = db.scalar(
                select(Job.state)
                .join(Analysis, Analysis.job_id == Job.id)
                .where(Analysis.id == item["analysis_id"])
            )
        item["job_id"] = db.scalar(
            select(Job.id).where(Job.source_id == source.id).order_by(Job.created_at.desc()).limit(1)
        )
        result.append(item)
    return result


@router.post("/sources/text", status_code=202, response_model=SourceCreated)
def text_source(
    data: TextInput,
    db: Db,
    user: CurrentUser,
    idempotency_key: str | None = Header(default=None, max_length=160),
):
    raw = data.text.encode("utf-8")
    if len(raw) > settings().max_upload_bytes:
        raise HTTPException(413, "Document exceeds the upload limit.")
    # Enforce text format irrespective of an optional display title.
    name = data.name if data.name.lower().endswith(".txt") else data.name + ".txt"
    previous = existing_ingest(db, user, idempotency_key, raw, name)
    if previous:
        return previous
    quota(db, user)
    source, job = create_source(db, user, raw, name, "text")
    ingestion_key(job, idempotency_key, raw, name)
    db.commit()
    return accepted(source, job)


@router.post("/sources/upload", status_code=202, response_model=SourceCreated)
async def upload_source(
    db: Db,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    idempotency_key: str | None = Header(default=None, max_length=160),
):
    name = file.filename or "document"
    if Path(name).suffix.lower() not in (".pdf", ".docx", ".txt", ".html", ".htm"):
        raise HTTPException(422, "Supported formats: PDF, DOCX, TXT and HTML.")
    data = await file.read(settings().max_upload_bytes + 1)
    await file.close()
    if not data:
        raise HTTPException(422, "The file is empty.")
    if len(data) > settings().max_upload_bytes:
        raise HTTPException(413, "The file exceeds the configured upload limit.")
    previous = existing_ingest(db, user, idempotency_key, data, name)
    if previous:
        return previous
    quota(db, user)
    source, job = create_source(db, user, data, name)
    ingestion_key(job, idempotency_key, data, name)
    db.commit()
    return accepted(source, job)


@router.get("/sources/{source_id}", response_model=SourceResponse)
def get_source(source_id: str, db: Db, user: CurrentUser):
    source = owned(db, Source, source_id, user)
    sections = db.scalars(select(Section).where(Section.source_id == source.id).order_by(Section.ordinal))
    job = db.scalar(select(Job).where(Job.source_id == source.id).order_by(Job.created_at.desc()).limit(1))
    return {
        **source_dict(source),
        "sections": [s.data for s in sections],
        "job_id": job.id if job else None,
        "processing_error": job.error if job else None,
        "job_state": job.state if job else None,
    }


@router.patch("/sources/{source_id}", response_model=SourceResponse)
def rename_source(source_id: str, data: RenameInput, db: Db, user: CurrentUser):
    source = owned(db, Source, source_id, user)
    if not data.name.strip():
        raise HTTPException(422, "Enter a document display name.")
    source.details = {**source.details, "display_name": data.name.strip()}
    db.commit()
    return source_dict(source)


@router.get("/sources/{source_id}/sections/{section_id}", response_model=SectionResponse)
def get_section(source_id: str, section_id: str, db: Db, user: CurrentUser):
    owned(db, Source, source_id, user)
    section = db.get(Section, section_id)
    if not section or section.source_id != source_id:
        raise HTTPException(404, "Section unavailable.")
    return section.data


@router.get("/sources/{source_id}/original")
def original(source_id: str, db: Db, user: CurrentUser):
    source = owned(db, Source, source_id, user)
    if source.kind == "url":
        raise HTTPException(
            403,
            "Redistribution of captured third-party pages is disabled. Inspect extracted evidence instead.",
        )
    data = storage.read(source.object_key, source.sha256)
    # Attachment only: never execute uploaded HTML in application origin.
    return Response(
        data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=document" + Path(source.original_name).suffix,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/sources/{source_id}", status_code=204)
def remove_source(source_id: str, db: Db, user: CurrentUser):
    keys = delete_source(db, owned(db, Source, source_id, user))
    db.commit()
    flush_storage_deletions(db)
    if db.scalar(select(StorageDeletion.id).where(StorageDeletion.object_key.in_(keys)).limit(1)):
        return JSONResponse(
            {
                "status": "DELETION_PENDING",
                "message": "Access revoked. Private file deletion is queued for retry.",
            },
            status_code=202,
        )


@router.post("/discovery", status_code=202, response_model=JobCreated)
def start_discovery(
    data: DiscoveryInput,
    db: Db,
    user: CurrentUser,
    idempotency_key: str | None = Header(default=None, max_length=160),
):
    if idempotency_key:
        previous = db.scalar(
            select(Job).where(Job.owner_id == user.id, Job.idempotency_key == idempotency_key)
        )
        if previous:
            if previous.kind != "discovery" or previous.payload != {"url": data.url}:
                raise HTTPException(409, "Idempotency key was already used for a different request.")
            return {"job_id": previous.id}
    throttle(db, "discovery:" + user.id, 10, 3600)
    quota(db, user)
    job = Job(owner_id=user.id, kind="discovery", payload={"url": data.url}, idempotency_key=idempotency_key)
    db.add(job)
    db.commit()
    return {"job_id": job.id}


@router.get("/discovery/{job_id}", response_model=DiscoveryResponse)
def discovery_result(job_id: str, db: Db, user: CurrentUser):
    job = owned(db, Job, job_id, user)
    if job.kind != "discovery":
        raise HTTPException(404, "Discovery unavailable.")
    return {"job_id": job.id, "state": job.state, "error": job.error, **job.result}


@router.post("/sources/url", status_code=202, response_model=SourceCreated)
def url_source(data: URLInput, db: Db, user: CurrentUser):
    quota(db, user)
    discovery = owned(db, Job, data.discovery_job_id, user)
    if discovery.kind != "discovery" or discovery.state != "COMPLETED":
        raise HTTPException(409, "Wait for discovery to finish.")
    candidate = next(
        (
            c
            for c in discovery.result.get("candidates", [])
            if c["url"] == data.url and c["status"] == "AVAILABLE"
        ),
        None,
    )
    if not candidate:
        raise HTTPException(422, "Select an accessible candidate from this discovery.")
    # Return a reserved source ID; worker captures only after user selection.
    ident = uid()
    job = Job(
        owner_id=user.id,
        kind="capture",
        payload={"source_id": ident, "url": data.url, "discovered_from": candidate.get("discovered_from")},
    )
    db.add(job)
    db.commit()
    return {"source_id": ident, "job_id": job.id}
