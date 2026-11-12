"""Terminal-state recovery for expired leases/deadlines; never replay model requests."""

from sqlalchemy import func, select

from app.models import Analysis, Finding, Job, now


def fail_processing(db, job_id, token, reason, *, commit=True):
    job = db.scalar(
        select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True)
    )
    if not job or job.state != "PROCESSING" or job.lease_token != token:
        return False
    if reason.startswith("WORKER_LEASE_EXPIRED") and job.lease_until is not None and (
        job.lease_until.replace(tzinfo=now().tzinfo) >= now()
    ):
        return False
    analysis = db.scalar(select(Analysis).where(Analysis.job_id == job_id))
    retained = (
        db.scalar(select(func.count()).select_from(Finding).where(Finding.analysis_id == analysis.id))
        if analysis
        else 0
    )
    job.state = "PARTIAL_COMPLETION" if retained else "FAILED"
    job.stage = job.state
    job.error = reason
    job.lease_token = None
    job.lease_until = None
    if analysis:
        coverage = dict(analysis.coverage or {})
        coverage["warnings"] = [*coverage.get("warnings", []), reason]
        analysis.coverage = coverage
    if commit:
        db.commit()
    return True
