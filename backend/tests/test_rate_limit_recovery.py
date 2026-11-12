"""Synthetic/replayed HTTP only; never exercises live provider credentials."""

import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from conftest import login_guest
from sqlalchemy import select
from test_api import upload_text

from app import worker
from app.config import settings
from app.db import SessionLocal
from app.models import AnalysisCheckpoint, Finding, Job, RateBucket, User, now
from app.providers.base import ProviderError
from app.services.rate_limit_recovery import pause


def expire_cooldown(job_id):
    with SessionLocal() as db:
        db.get(Job, job_id).lease_until = now() - timedelta(seconds=1)
        for row in db.scalars(select(RateBucket).where(RateBucket.id.like("ai-cooldown:%"))):
            row.expires_at = now() - timedelta(seconds=1)
        db.commit()


def test_429_preserves_finding_then_resumes_only_unfinished_inference(client, monkeypatch):
    login_guest(client)
    source = upload_text(
        client, "Invoices are due within thirty days.\n\nCustomer must keep passwords secret."
    )
    monkeypatch.setattr(settings(), "gemini_api_key", "synthetic")
    monkeypatch.setattr(settings(), "gemini_model", "synthetic")
    original, sent = httpx.Client, []

    def handler(request):
        prompt = json.loads(request.content)["contents"][0]["parts"][0]["text"]
        sent.append(prompt)
        if prompt.startswith("Extract"):
            passages = json.loads(prompt[prompt.index("[") :])
            result = {
                "findings": [
                    {
                        "source_id": p["source_id"],
                        "section_id": p["section_id"],
                        "page": p["page"],
                        "quote": p["text"],
                        "start": p["start_offset"],
                        "end": p["end_offset"],
                        "category": "OBLIGATION",
                        "statement": p["text"],
                        "rationale": "Stated obligation",
                        "qualifications": [],
                        "cross_references": [],
                    }
                    for p in passages
                ]
            }
        elif len(sent) == 3:
            # The recorded live failure occurred after successful semantic verdicts.
            recorded = json.loads(
                (Path(__file__).parents[2] / "docs/benchmarks/final_live_acceptance.json").read_text()
            )
            assert recorded["error"] == "LIVE_PROVIDER_HTTP_429"
            return httpx.Response(
                429, json={"error": {"message": "Synthetic quota response"}}, headers={"Retry-After": "90"}
            )
        else:
            result = {
                "support_status": "SUPPORTED",
                "rationale": "The quoted obligation is explicit.",
                "missing_qualifiers": [],
                "unresolved_references": [],
                "category_consistent": True,
            }
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(result)}]}}]
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: pytest.fail("429 cannot busy retry"))
    submitted = client.post(
        "/api/v1/analyses",
        json={
            "source_ids": [source["source_id"]],
            "provider": "gemini",
            "consent": True,
            "privacy_mode": "external",
        },
    ).json()
    jid, aid = submitted["job_id"], submitted["analysis_id"]
    assert worker.run_once()
    waiting = client.get(f"/api/v1/jobs/{jid}").json()
    assert waiting["state"] == "WAITING_RATE_LIMIT" and len(sent) == 3
    assert waiting["progress"]["automatic_resume"] == 1
    assert (json_time(waiting["progress"]["resume_at"]) - now()).total_seconds() > 85
    assert not worker.run_once()  # not due; no polling-triggered inference
    retained = client.get(f"/api/v1/analyses/{aid}/findings").json()
    assert len(retained) == 1 and retained[0]["support_status"] == "SUPPORTED"
    summary = client.get(f"/api/v1/analyses/{aid}/summary").json()["summary"]
    assert summary["level"] == "Not Determinable" and not summary["assessment_complete"]
    assert (
        client.post(f"/api/v1/analyses/{aid}/questions", json={"question": "What must I pay?"}).status_code
        == 409
    )
    expire_cooldown(jid)
    assert worker.run_once()
    assert client.get(f"/api/v1/jobs/{jid}").json()["state"] == "COMPLETED"
    # Candidate generation and first verdict are cached. Only the rejected request is reissued.
    assert len(sent) == 4 and sent[2] == sent[3]
    assert len(client.get(f"/api/v1/analyses/{aid}/findings").json()) == 2
    with SessionLocal() as db:
        assert len(db.scalars(select(Finding)).all()) == 2
        assert len(db.scalars(select(AnalysisCheckpoint)).all()) == 4


def json_time(value):
    from datetime import datetime

    return datetime.fromisoformat(value)


@pytest.mark.parametrize(
    "blocker", ["uncertain", "disabled", "attempt_limit", "long_wait", "budget", "daily_quota"]
)
def test_unsafe_or_unbounded_recovery_is_not_scheduled(client, monkeypatch, blocker):
    owner = login_guest(client)["id"]
    with SessionLocal() as db:
        job = Job(owner_id=owner, kind="analysis", state="PROCESSING", lease_token="current", attempts=1)
        db.add(job)
        db.flush()
        if blocker == "uncertain":
            db.add(
                AnalysisCheckpoint(
                    job_id=job.id, request_hash="unknown", state="RUNNING", reserved_tokens=10, data={}
                )
            )
        if blocker == "disabled":
            monkeypatch.setattr(settings(), "ai_rate_limit_max_resumes", 0)
        if blocker == "attempt_limit":
            job.attempts = 3
        if blocker == "budget":
            monkeypatch.setattr(settings(), "max_ai_calls_per_operation", 1)
            db.add(
                AnalysisCheckpoint(
                    job_id=job.id, request_hash="failed", state="FAILED", reserved_tokens=10, data={}
                )
            )
        db.commit()
        error = ProviderError(
            "PROVIDER_RATE_LIMITED",
            calls=[
                {
                    "outcome": "PROVIDER_RATE_LIMITED",
                    "retry_after_seconds": 90000 if blocker == "long_wait" else 60,
                }
            ],
        )
        if blocker == "daily_quota":
            error.model_calls[0].update(quota_scope="daily", retry_after_source="conservative_default")
        assert not pause(db, job.id, "current", error)
        assert db.get(Job, job.id).state == "PROCESSING"
        assert db.get(Job, job.id).result["rate_limit_recovery"]["stop_reason"]


def test_repeated_429_stops_after_two_durable_resumes(client, monkeypatch):
    owner = login_guest(client)["id"]
    monkeypatch.setattr(settings(), "gemini_api_key", "synthetic")
    monkeypatch.setattr(settings(), "gemini_model", "synthetic")
    source = upload_text(client, "Customer must pay invoices.")
    original, calls = httpx.Client, []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    item = client.post(
        "/api/v1/analyses",
        json={
            "source_ids": [source["source_id"]],
            "provider": "gemini",
            "consent": True,
            "privacy_mode": "external",
        },
    ).json()
    for expected in ("WAITING_RATE_LIMIT", "WAITING_RATE_LIMIT", "FAILED"):
        assert worker.run_once()
        assert client.get(f"/api/v1/jobs/{item['job_id']}").json()["state"] == expected
        expire_cooldown(item["job_id"])
    assert len(calls) == 3 and not worker.run_once()
    with SessionLocal() as db:
        assert db.get(User, owner)


def test_cancellation_during_cooldown(client):
    owner = login_guest(client)["id"]
    with SessionLocal() as db:
        job = Job(owner_id=owner, kind="analysis", state="PROCESSING", lease_token="current", attempts=1)
        db.add(job)
        db.commit()
        assert pause(db, job.id, "current", ProviderError("PROVIDER_RATE_LIMITED"))
        jid = job.id
    assert client.post(f"/api/v1/jobs/{jid}/cancel").status_code == 200
    expire_cooldown(jid)
    assert not worker.run_once()


def test_revocation_is_rechecked_after_cooldown(client, monkeypatch):
    owner = login_guest(client)["id"]
    source = upload_text(client, "Customer must pay invoices.")
    monkeypatch.setattr(settings(), "gemini_api_key", "synthetic")
    monkeypatch.setattr(settings(), "gemini_model", "synthetic")
    original, sent = httpx.Client, []

    def handler(request):
        sent.append(request)
        return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    submitted = client.post(
        "/api/v1/analyses",
        json={
            "source_ids": [source["source_id"]],
            "provider": "gemini",
            "consent": True,
            "privacy_mode": "external",
        },
    ).json()
    assert worker.run_once()
    with SessionLocal() as db:
        db.get(User, owner).authorized_providers = []
        db.commit()
    expire_cooldown(submitted["job_id"])
    assert worker.run_once()
    job = client.get(f"/api/v1/jobs/{submitted['job_id']}").json()
    assert job["state"] == "FAILED" and "PROVIDER_PERMISSION_REVOKED" in job["error"]
    assert len(sent) == 1


def test_safe_quota_diagnostics_redact_prose_and_classify_only_known_scopes():
    from app.providers.diagnostics import error_details

    response = httpx.Response(
        429,
        headers={"x-ratelimit-limit": "20", "x-ratelimit-remaining": "0", "x-ratelimit-reset": "PRIVATE"},
        json={
            "error": {
                "code": "rate_limit_exceeded",
                "message": "Requests per day exhausted PRIVATE document text",
            }
        },
    )
    details = error_details(response)
    assert details["quota_scope"] == "daily" and details["quota_limit"] == 20
    assert details["quota_remaining"] == 0 and "quota_reset" not in details
    assert "PRIVATE" not in json.dumps(details)
