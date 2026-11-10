"""Job-scoped request cache; uncertain in-flight requests require explicit retry acknowledgment."""

import hashlib
import json

from sqlalchemy import func, select

from app.models import AnalysisCheckpoint, Job
from app.providers.base import ProviderError


class RequestCheckpoints:
    def __init__(self, factory, job_id, lease_token):
        self.factory, self.job_id, self.lease_token = factory, job_id, lease_token

    def begin(self, payload, schema, role, metadata, estimated, budget):
        logical = json.loads(json.dumps(payload))
        logical.pop("max_tokens", None)
        if "generationConfig" in logical:
            logical["generationConfig"].pop("maxOutputTokens", None)
        fingerprint = hashlib.sha256(
            json.dumps(
                {"payload": logical, "schema": schema, "role": role, "version": metadata["prompt_version"]},
                sort_keys=True,
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        with self.factory() as db:
            job = db.scalar(
                select(Job)
                .where(Job.id == self.job_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not job or job.state != "PROCESSING" or job.lease_token != self.lease_token:
                raise ProviderError("PROVIDER_JOB_INTERRUPTED")
            completed = db.scalar(
                select(AnalysisCheckpoint)
                .where(
                    AnalysisCheckpoint.job_id == self.job_id,
                    AnalysisCheckpoint.request_hash == fingerprint,
                    AnalysisCheckpoint.state == "COMPLETED",
                )
                .order_by(AnalysisCheckpoint.created_at.desc())
            )
            if completed:
                return None, completed.data
            uncertain = db.scalar(
                select(AnalysisCheckpoint.id)
                .where(AnalysisCheckpoint.job_id == self.job_id, AnalysisCheckpoint.state == "RUNNING")
                .limit(1)
            )
            if uncertain:
                raise ProviderError("PROVIDER_CHECKPOINT_UNCERTAIN")
            calls, tokens = db.execute(
                select(func.count(), func.coalesce(func.sum(AnalysisCheckpoint.reserved_tokens), 0)).where(
                    AnalysisCheckpoint.job_id == self.job_id
                )
            ).one()
            if calls >= budget["max_calls"] or tokens + estimated > budget["max_tokens"]:
                raise ProviderError("PROVIDER_OPERATION_BUDGET_EXCEEDED")
            record = AnalysisCheckpoint(
                job_id=self.job_id,
                request_hash=fingerprint,
                state="RUNNING",
                reserved_tokens=estimated,
                data={"metadata": metadata},
            )
            db.add(record)
            db.flush()
            ident = record.id
            db.commit()
            return ident, None

    def finish(self, ident, value, metadata):
        with self.factory() as db:
            record = db.get(AnalysisCheckpoint, ident)
            record.state = "COMPLETED"
            record.data = {"value": value, "metadata": metadata}
            db.commit()

    def fail(self, ident, code):
        with self.factory() as db:
            record = db.get(AnalysisCheckpoint, ident)
            if record and record.state == "RUNNING":
                record.state = "FAILED"
                record.data = {"code": code, **record.data}
                db.commit()
