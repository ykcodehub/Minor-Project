from fastapi import APIRouter
from sqlalchemy import func, select

from app.models import Analysis, AnalysisSource, AuditEvent, Job, Source, now
from app.schemas import DashboardResponse
from app.security import CurrentUser, Db
from app.services.resources import source_dict

router = APIRouter()


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: Db, user: CurrentUser):
    source_scope = select(Source.id).where(Source.owner_id == user.id, Source.expires_at > now())
    analyses = (
        select(Analysis.id)
        .join(AnalysisSource)
        .where(Analysis.owner_id == user.id, AnalysisSource.source_id.in_(source_scope))
        .distinct()
    )
    states = dict(
        db.execute(
            select(Job.state, func.count())
            .join(Analysis, Analysis.job_id == Job.id)
            .where(Analysis.id.in_(analyses))
            .group_by(Job.state)
        ).all()
    )
    recent = []
    for source in db.scalars(
        select(Source).where(Source.id.in_(source_scope)).order_by(Source.captured_at.desc()).limit(6)
    ):
        item = source_dict(source)
        item["analysis_id"] = db.scalar(
            select(AnalysisSource.analysis_id)
            .join(Analysis)
            .where(AnalysisSource.source_id == source.id)
            .order_by(Analysis.created_at.desc())
            .limit(1)
        )
        recent.append(item)
    return {
        "counts": {
            "documents": db.scalar(select(func.count()).select_from(source_scope.subquery())),
            "completed_analyses": states.get("COMPLETED", 0) + states.get("PARTIAL_COMPLETION", 0),
            "pending_analyses": states.get("QUEUED", 0)
            + states.get("PROCESSING", 0)
            + states.get("WAITING_RATE_LIMIT", 0),
            "failed_analyses": states.get("FAILED", 0),
        },
        "recent_documents": recent,
        "recent_activity": [
            {
                "action": e.action,
                "object_id": e.object_id,
                "created_at": e.created_at.replace(tzinfo=now().tzinfo).isoformat(),
            }
            for e in db.scalars(
                select(AuditEvent)
                .where(AuditEvent.actor_id == user.id)
                .order_by(AuditEvent.created_at.desc())
                .limit(10)
            )
        ],
    }
