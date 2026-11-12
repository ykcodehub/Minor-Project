"""Recorded failure shapes, synthetic HTTP only. No real inference or production writes."""

import json
from datetime import timedelta

import httpx
import pytest
from conftest import login_guest
from test_api import upload_text

from app import worker
from app.config import settings
from app.db import SessionLocal
from app.models import Job, now
from app.providers.base import ProviderError, configured_provider
from app.services.analysis import CandidateBatch


def test_actual_failure_shapes_recover_to_persisted_summary(client, monkeypatch, caplog):
    login_guest(client)
    source = upload_text(client, "Payment is due within thirty days.")
    for name, model in [
        ("gemini", "gemini-3.6-flash"),
        ("groq", "openai/gpt-oss-20b"),
        ("openrouter", "test/structured:free"),
    ]:
        monkeypatch.setattr(settings(), name + "_api_key", "synthetic")
        monkeypatch.setattr(settings(), name + "_model", model)
    original = httpx.Client
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append((request.url.host, payload))
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(503)
        prompt = payload["messages"][1]["content"]
        if request.url.host == "openrouter.ai":
            count = sum(host == request.url.host for host, _ in seen)
            if count == 1:
                return httpx.Response(
                    200,
                    json={
                        "choices": [{"finish_reason": "length", "message": {"content": ""}}],
                        "usage": {
                            "completion_tokens": 4096,
                            "completion_tokens_details": {"reasoning_tokens": 4096},
                        },
                    },
                )
            return httpx.Response(
                200, json={"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]}
            )
        assert payload["model"] == "openai/gpt-oss-20b" and payload["reasoning_effort"] == "low"
        schema = payload["response_format"]["json_schema"]["schema"]
        if '"minLength"' in json.dumps(schema):
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": "invalid_json_schema",
                        "param": "response_format.json_schema.schema",
                        "message": "Unsupported schema constraint. CONFIDENTIAL RESPONSE MUST NOT LEAK",
                        "failed_generation": "PRIVATE DOCUMENT",
                    }
                },
            )
        assert payload["response_format"]["json_schema"]["strict"] is True
        if prompt.startswith("Extract"):
            p = json.loads(prompt[prompt.index("[") :])[0]
            data = {
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
                        "rationale": "Stated",
                        "qualifications": [],
                        "cross_references": [],
                    }
                ]
            }
        else:
            data = {
                "support_status": "SUPPORTED",
                "rationale": "Stated",
                "missing_qualifiers": [],
                "unresolved_references": [],
            }
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(data)}}]}
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: None)
    submitted = client.post(
        "/api/v1/analyses",
        json={
            "source_ids": [source["source_id"]],
            "provider": "gemini",
            "fallback_providers": ["openrouter", "groq"],
            "consent": True,
            "privacy_mode": "external",
        },
    )
    assert submitted.status_code == 202 and worker.run_once()
    job = client.get(f"/api/v1/jobs/{submitted.json()['job_id']}").json()
    assert job["state"] == "COMPLETED"
    summary = client.get(f"/api/v1/analyses/{submitted.json()['analysis_id']}/summary").json()["summary"]
    assert (
        summary["counts"]["verified"] == 1
        and summary["groups"]["obligations"][0]["citations"][0]["quote"]
        == "Payment is due within thirty days."
    )
    calls = client.get(f"/api/v1/analyses/{submitted.json()['analysis_id']}").json()["model_calls"]
    assert any(c.get("reasoning_tokens") == 4096 for c in calls)
    assert any(
        c.get("provider_error_code") == "invalid_json_schema"
        and c.get("validation_issue") == "SCHEMA_UNSUPPORTED"
        for c in calls
    )
    assert "CONFIDENTIAL" not in caplog.text and "PRIVATE DOCUMENT" not in caplog.text


def test_complete_json_fence_supported_but_partial_json_rejected(monkeypatch):
    original = httpx.Client

    def install(content):
        monkeypatch.setattr(
            httpx,
            "Client",
            lambda **kw: original(
                transport=httpx.MockTransport(
                    lambda req: httpx.Response(
                        200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
                    )
                ),
                **kw,
            ),
        )

    provider = configured_provider(
        {"name": "openrouter", "model": "test/structured:free", "key": "synthetic", "retries": 0}
    )
    install('```json\n{"findings":[]}\n```')
    assert provider.generate("s", "p", CandidateBatch, "candidate_generation")[0].findings == []
    install('```json\n{"findings":[\n```')
    with pytest.raises(ProviderError, match="PROVIDER_INVALID_OUTPUT"):
        provider.generate("s", "p", CandidateBatch, "candidate_generation")


def test_expired_processing_is_terminal_on_owned_poll_without_worker(client):
    login_guest(client)
    owner = client.get("/api/v1/me").json()["id"]
    with SessionLocal() as db:
        job = Job(
            owner_id=owner,
            kind="analysis",
            state="PROCESSING",
            lease_token="old",
            lease_until=now() - timedelta(seconds=1),
        )
        db.add(job)
        db.commit()
        ident = job.id
    result = client.get(f"/api/v1/jobs/{ident}").json()
    assert result["state"] == "FAILED" and "WORKER_LEASE_EXPIRED" in result["error"]


def test_deadline_stops_fresh_requests_without_billing(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("HTTP forbidden after deadline")

    monkeypatch.setattr(httpx.Client, "post", forbidden)
    p = configured_provider(
        {
            "name": "groq",
            "model": "openai/gpt-oss-20b",
            "key": "synthetic",
            "budget": {"calls": 0, "tokens": 0, "max_calls": 100, "max_tokens": 500000, "deadline": 0},
        }
    )
    with pytest.raises(ProviderError, match="ANALYSIS_DEADLINE_EXCEEDED"):
        p.generate("s", "p", CandidateBatch, "candidate_generation")


def test_watchdog_persists_terminal_failure_for_blocked_process(client, monkeypatch):
    login_guest(client)
    owner = client.get("/api/v1/me").json()["id"]
    with SessionLocal() as db:
        job = Job(owner_id=owner, kind="analysis")
        db.add(job)
        db.commit()
        ident = job.id
    callbacks = []

    class Timer:
        def __init__(self, seconds, callback):
            callbacks.append(callback)

        def start(self):
            pass

        def cancel(self):
            pass

    monkeypatch.setattr(worker.threading, "Timer", Timer)
    monkeypatch.setattr(worker, "process", lambda *args: callbacks[0]())
    assert worker.run_once()
    result = client.get(f"/api/v1/jobs/{ident}").json()
    assert result["state"] == "FAILED" and "ANALYSIS_DEADLINE_EXCEEDED" in result["error"]


def test_schema_compatibility_preserves_property_names_and_local_bounds():
    from pydantic import BaseModel, Field, ValidationError

    from app.providers.diagnostics import strict_wire_schema

    class Output(BaseModel):
        title: str = Field(min_length=3)

    wire = strict_wire_schema(Output.model_json_schema())
    assert "title" in wire["properties"] and wire["required"] == ["title"]
    assert "minLength" not in wire["properties"]["title"]
    assert wire["additionalProperties"] is False
    with pytest.raises(ValidationError):
        Output.model_validate({"title": "x"})


def test_unclassified_400_is_not_blindly_retried_or_logged(monkeypatch, caplog):
    original = httpx.Client
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "PRIVATE",
                    "param": "PERSONAL",
                    "message": "PRIVATE DOCUMENT",
                    "failed_generation": "PRIVATE",
                }
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    p = configured_provider({"name": "groq", "model": "openai/gpt-oss-20b", "key": "synthetic"})
    with pytest.raises(ProviderError, match="PROVIDER_REQUEST_REJECTED") as exc:
        p.generate("s", "p", CandidateBatch, "candidate_generation")
    assert len(calls) == 1
    assert exc.value.model_calls[0]["validation_issue"] == "DETAILS_REDACTED"
    assert "PRIVATE" not in caplog.text and "PERSONAL" not in caplog.text


def test_deadline_preserves_saved_findings_and_checks_lease(client):
    from app.models import Analysis, Finding
    from app.services.job_state import fail_processing

    login_guest(client)
    owner = client.get("/api/v1/me").json()["id"]
    with SessionLocal() as db:
        job = Job(owner_id=owner, kind="analysis", state="PROCESSING", lease_token="current")
        db.add(job)
        db.flush()
        analysis = Analysis(owner_id=owner, job_id=job.id)
        db.add(analysis)
        db.flush()
        db.add(Finding(analysis_id=analysis.id, data={"support_status": "AMBIGUOUS"}))
        db.commit()
        assert not fail_processing(db, job.id, "stale", "ANALYSIS_DEADLINE_EXCEEDED")
        assert fail_processing(db, job.id, "current", "ANALYSIS_DEADLINE_EXCEEDED")
        db.refresh(job)
        assert job.state == "PARTIAL_COMPLETION"
        assert db.get(Finding, db.query(Finding.id).first()[0]).data["support_status"] == "AMBIGUOUS"
        assert not fail_processing(db, job.id, "current", "overwrite")


def test_groq_generated_schema_failure_gets_one_changed_retry(monkeypatch):
    original = httpx.Client
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": "json_validate_failed",
                        "message": "Failed to generate JSON",
                        "failed_generation": "PRIVATE",
                    }
                },
            )
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"findings":[]}'}}]}
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: None)
    p = configured_provider({"name": "groq", "model": "openai/gpt-oss-20b", "key": "synthetic"})
    value, calls = p.generate("s", "p", CandidateBatch, "candidate_generation")
    assert not value.findings and calls[0]["outcome"] == "PROVIDER_INVALID_OUTPUT"
    assert len(requests) == 2 and requests[0] != requests[1]


def test_stale_lease_observation_cannot_override_fresh_heartbeat(client):
    from app.services.job_state import fail_processing

    login_guest(client)
    owner = client.get("/api/v1/me").json()["id"]
    with SessionLocal() as db:
        job = Job(
            owner_id=owner,
            kind="analysis",
            state="PROCESSING",
            lease_token="current",
            lease_until=now() + timedelta(minutes=1),
        )
        db.add(job)
        db.commit()
        assert not fail_processing(db, job.id, "current", "WORKER_LEASE_EXPIRED")
        db.refresh(job)
        assert job.state == "PROCESSING"
