"""Durable, bounded analysis pauses. Never replay uncertain requests automatically."""

import math
from datetime import timedelta

from sqlalchemy import func, select

from app.config import settings
from app.models import AnalysisCheckpoint, Job, now


def pause(db, job_id, token, error):
    if error.code != "PROVIDER_RATE_LIMITED":
        return False
    job = db.scalar(
        select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True)
    )
    if not job or job.kind != "analysis" or job.state != "PROCESSING" or job.lease_token != token:
        return False
    uncertain = db.scalar(
        select(AnalysisCheckpoint.id)
        .where(AnalysisCheckpoint.job_id == job_id, AnalysisCheckpoint.state == "RUNNING")
        .limit(1)
    )
    recovery = dict((job.result or {}).get("rate_limit_recovery", {}))
    resumes = recovery.get("resumes", 0)
    cfg = settings()
    calls, tokens = db.execute(
        select(func.count(), func.coalesce(func.sum(AnalysisCheckpoint.reserved_tokens), 0)).where(
            AnalysisCheckpoint.job_id == job_id
        )
    ).one()

    def decline(reason):
        job.result = {**(job.result or {}), "rate_limit_recovery": {**recovery, "stop_reason": reason}}
        return False

    if uncertain:
        return decline("UNCERTAIN_REQUEST_REQUIRES_MANUAL_REVIEW")
    if resumes >= cfg.ai_rate_limit_max_resumes or job.attempts >= 3:
        return decline("AUTOMATIC_RESUME_LIMIT_REACHED")
    if calls >= cfg.max_ai_calls_per_operation or tokens >= cfg.max_ai_tokens_per_operation:
        return decline("OPERATION_BUDGET_EXHAUSTED")
    if any(
        c.get("quota_scope") == "daily" and c.get("retry_after_source") != "provider"
        for c in error.model_calls
        if c.get("outcome") == "PROVIDER_RATE_LIMITED"
    ):
        return decline("DAILY_QUOTA_RESET_UNCONFIRMED")
    waits = [
        c.get("retry_after_seconds", 0)
        for c in error.model_calls
        if c.get("outcome") == "PROVIDER_RATE_LIMITED"
        and isinstance(c.get("retry_after_seconds", 0), (int, float))
        and math.isfinite(c.get("retry_after_seconds", 0))
    ]
    # Unknown quotas use bounded exponential delays, never a tight immediate loop.
    seconds = max(60 * (2**resumes), max(waits, default=0))
    if seconds > cfg.ai_rate_limit_max_wait_seconds:
        # Never shorten a provider-requested wait to fit application policy.
        return decline("PROVIDER_WAIT_EXCEEDS_AUTOMATIC_POLICY")
    resume_at = now() + timedelta(seconds=math.ceil(seconds))
    job.result = {
        **(job.result or {}),
        "rate_limit_recovery": {
            "resumes": resumes + 1,
            "max_resumes": cfg.ai_rate_limit_max_resumes,
            "resume_at": resume_at.isoformat(),
            "reason": "PROVIDER_RATE_LIMITED",
        },
    }
    job.state, job.stage = "WAITING_RATE_LIMIT", "RATE_LIMIT_COOLDOWN"
    job.error = "PROVIDER_RATE_LIMITED: Analysis paused. Validated findings are retained; processing will resume after cooldown. Coverage is incomplete."
    job.progress = {
        **(job.progress or {}),
        "resume_at": resume_at.isoformat(),
        "automatic_resume": resumes + 1,
        "max_automatic_resumes": cfg.ai_rate_limit_max_resumes,
    }
    # For a waiting job only, lease_until is the durable not-before timestamp.
    job.lease_token, job.lease_until = None, resume_at
    db.commit()
    return True
