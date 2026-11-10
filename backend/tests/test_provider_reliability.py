"""Provider reliability with synthetic HTTP only; no live API calls."""

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from pydantic import BaseModel

from app.providers.base import ProviderError, configured_provider

ORIGINAL_CLIENT = httpx.Client


class Output(BaseModel):
    answer: str


def setup_provider(monkeypatch, responses, retries=2):
    original = ORIGINAL_CLIENT
    requests, sleeps = [], []

    def handle(request):
        requests.append(json.loads(request.content))
        response = responses[min(len(requests) - 1, len(responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    monkeypatch.setattr("app.providers.base.time.sleep", sleeps.append)
    return (
        configured_provider(
            {"name": "gemini", "model": "gemini-test", "key": "private-key", "retries": retries}
        ),
        requests,
        sleeps,
    )


def success():
    return httpx.Response(
        200,
        json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"answer":"ok"}'}]}}]},
    )


def test_503_retry_after_and_success(monkeypatch, caplog):
    p, requests, sleeps = setup_provider(
        monkeypatch,
        [
            httpx.Response(503, headers={"Retry-After": "5"}, json={"error": {"message": "private source"}}),
            success(),
        ],
    )
    value, calls = p.generate("private system", "private text", Output, "candidate_generation")
    assert value.answer == "ok" and len(requests) == 2
    assert sleeps == [5]
    assert calls[0]["http_status"] == 503 and calls[1]["finish_reason"] == "STOP"
    assert "private" not in caplog.text
    assert "PROVIDER_UNAVAILABLE" in caplog.text


@pytest.mark.parametrize("date_header", [False, True])
def test_long_retry_after_never_retries_early(monkeypatch, date_header):
    header = format_datetime(datetime.now(UTC) + timedelta(minutes=5)) if date_header else "120"
    p, requests, sleeps = setup_provider(monkeypatch, [httpx.Response(503, headers={"Retry-After": header})])
    with pytest.raises(ProviderError):
        p.generate("s", "p", Output, "candidate_generation")
    assert len(requests) == 1 and not sleeps


def test_max_tokens_bounded_budget_recovery(monkeypatch):
    limited = httpx.Response(200, json={"candidates": [{"finishReason": "MAX_TOKENS"}]})
    p, requests, _sleeps = setup_provider(monkeypatch, [limited, success()])
    value, calls = p.generate("s", "p", Output, "candidate_generation")
    assert value.answer == "ok"
    assert [r["generationConfig"]["maxOutputTokens"] for r in requests] == [4096, 8192]
    assert calls[0]["outcome"] == "PROVIDER_OUTPUT_LIMIT"
    p, requests, _sleeps = setup_provider(monkeypatch, [limited])
    with pytest.raises(ProviderError, match="PROVIDER_OUTPUT_LIMIT"):
        p.generate("s", "p", Output, "candidate_generation")
    assert len(requests) == 3
    assert requests[-1] != requests[-2]


@pytest.mark.parametrize(
    "raw", [{"candidates": [{"finishReason": "SAFETY"}]}, {"promptFeedback": {"blockReason": "SAFETY"}}]
)
def test_safety_block_not_retried(monkeypatch, raw):
    p, requests, sleeps = setup_provider(monkeypatch, [httpx.Response(200, json=raw)])
    with pytest.raises(ProviderError, match="PROVIDER_CONTENT_BLOCKED"):
        p.generate("s", "p", Output, "candidate_generation")
    assert len(requests) == 1 and not sleeps


@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(503), "PROVIDER_UNAVAILABLE"),
        (httpx.ReadTimeout("secret"), "PROVIDER_TIMEOUT"),
        (
            httpx.Response(
                200,
                json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}]},
            ),
            "PROVIDER_INVALID_OUTPUT",
        ),
    ],
)
def test_exhausted_retries_are_bounded(monkeypatch, response, code):
    p, requests, sleeps = setup_provider(monkeypatch, [response])
    with pytest.raises(ProviderError, match=code) as exc:
        p.generate("s", "p", Output, "candidate_generation")
    expected = 2 if code == "PROVIDER_INVALID_OUTPUT" else 3
    assert len(requests) == expected and len(sleeps) == expected - 1
    assert len(exc.value.model_calls) == expected
    assert 2 <= sleeps[0] <= 3
    if expected == 3:
        assert 4 <= sleeps[1] <= 5
    else:
        assert requests[0] != requests[1]


def test_worker_api_preserves_actionable_failure_and_retry_consent(client, monkeypatch):
    from conftest import login_guest
    from sqlalchemy import select

    from app import worker
    from app.config import settings
    from app.db import SessionLocal
    from app.models import Job, ModelCall

    login_guest(client)
    user = client.get("/api/v1/me").json()
    monkeypatch.setattr(settings(), "gemini_api_key", "synthetic-key")
    monkeypatch.setattr(settings(), "gemini_model", "gemini-test")
    payload = {"provider": "gemini", "fallback_providers": [], "consent": True}
    with SessionLocal() as db:
        job = Job(owner_id=user["id"], kind="analysis", payload=payload)
        db.add(job)
        db.commit()
        job_id = job.id
    call = {
        "provider": "gemini",
        "model": "gemini-test",
        "attempt": 1,
        "http_status": 200,
        "finish_reason": "MAX_TOKENS",
        "outcome": "PROVIDER_OUTPUT_LIMIT",
    }

    def fail(*args):
        raise ProviderError("ANALYSIS_GENERATION_FAILED", calls=[call])

    monkeypatch.setattr(worker, "process", fail)
    assert worker.run_once()
    response = client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["state"] == "FAILED"
    assert "PROVIDER_OUTPUT_LIMIT" in response.json()["error"]
    with SessionLocal() as db:
        saved = db.scalar(select(ModelCall).where(ModelCall.job_id == job_id))
        assert saved.data["finish_reason"] == "MAX_TOKENS"
    assert client.post(f"/api/v1/jobs/{job_id}/retry").status_code == 200
    with SessionLocal() as db:
        assert db.get(Job, job_id).payload == payload
