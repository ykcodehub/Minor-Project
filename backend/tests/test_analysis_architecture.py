"""Index coverage and restart safety; all provider HTTP is synthetic."""

import json

import httpx
import pytest
from conftest import login_guest
from test_api import upload_text

from app import worker
from app.config import settings
from app.db import SessionLocal
from app.models import Job
from app.providers.base import ProviderError, configured_provider
from app.services import analysis
from app.services.checkpoints import RequestCheckpoints
from app.services.context_index import SourceWideIndex, compact_passages, expand_citation


def test_compact_aliases_are_exact_reversible_and_scope_validated():
    passages = [
        {
            "source_id": "long-source",
            "section_id": "long-section",
            "page": 2,
            "start_offset": 5,
            "end_offset": 8,
            "text": "abc",
        }
    ]
    wire, aliases = compact_passages(passages)
    decoded = expand_citation(
        {"source_id": wire[0]["source_id"], "section_id": wire[0]["section_id"]}, aliases
    )
    assert decoded == {"source_id": "long-source", "section_id": "long-section"}
    assert (
        expand_citation({"source_id": "unknown", "section_id": "unknown"}, aliases)["section_id"] == "unknown"
    )


def test_source_index_scans_more_than_twelve_windows_once(monkeypatch):
    sections = [
        {"source_id": "src", "id": f"sec{i}", "page": i + 1, "text": ("Ordinary administrative text. " * 200)}
        for i in range(30)
    ]
    count = []

    def generate(configs, system, prompt, schema, role):
        count.append(role)
        return analysis.ContextAudit(relevant_passages=[], unresolved_context=False), [
            {"provider": "groq", "role": role}
        ]

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    index = SourceWideIndex(sections)
    config = {"name": "groq", "model": "synthetic", "key": "synthetic"}
    record, _calls = index.prepare("src", config)
    assert record["complete"] and record["windows_processed"] == record["windows_total"] > 12
    again, cached = index.prepare("src", config)
    assert again is record and not cached and len(count) == record["windows_total"]


def test_invalid_global_index_quote_never_becomes_supported(monkeypatch):
    sections = [{"source_id": "src", "id": "sec", "page": 1, "text": "Payment is due. " * 1500}]

    def generate(configs, system, prompt, schema, role):
        assert role == "context_indexing"
        return analysis.ContextAudit(
            relevant_passages=[
                analysis.SourceCitation(
                    source_id="s0", section_id="r0", page=1, quote="Fabricated source text", start=0, end=22
                )
            ],
            unresolved_context=False,
        ), []

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    index = SourceWideIndex(sections)
    candidate = {
        "source_id": "src",
        "section_id": "sec",
        "page": 1,
        "quote": "Payment is due.",
        "statement": "Payment is due.",
        "cross_references": [],
    }
    with pytest.raises(ProviderError, match="PROVIDER_INVALID_OUTPUT"):
        index.review(candidate, [{"name": "groq", "model": "synthetic", "key": "synthetic"}])


def test_checkpoint_cache_is_job_scoped_and_permission_guarded(client, monkeypatch):
    login_guest(client)
    owner = client.get("/api/v1/me").json()["id"]
    with SessionLocal() as db:
        jobs = [
            Job(owner_id=owner, kind="analysis", state="PROCESSING", lease_token=f"lease{i}")
            for i in range(2)
        ]
        db.add_all(jobs)
        db.commit()
        ids = [j.id for j in jobs]
    original = httpx.Client
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"findings":[]}'}]}}]
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    for index, ident in enumerate(ids):
        config = {
            "name": "gemini",
            "model": "synthetic",
            "key": "synthetic",
            "checkpoint": RequestCheckpoints(SessionLocal, ident, f"lease{index}"),
            "budget": {"calls": 0, "tokens": 0, "max_calls": 100, "max_tokens": 500000},
            "authorize": lambda: True,
        }
        p = configured_provider(config)
        p.generate("s", "p", analysis.CandidateBatch, "candidate_generation")
        _, calls = p.generate("s", "p", analysis.CandidateBatch, "candidate_generation")
        assert calls[0]["cached"] and calls[0]["token_in"] == 0
        p.authorize = lambda: False
        with pytest.raises(ProviderError, match="PROVIDER_PERMISSION_REVOKED"):
            p.generate("s", "p", analysis.CandidateBatch, "candidate_generation")
    assert len(seen) == 2


def test_uncertain_request_needs_ack_and_reservations_survive_retry(client, monkeypatch):
    login_guest(client)
    owner = client.get("/api/v1/me").json()["id"]
    monkeypatch.setattr(settings(), "gemini_api_key", "synthetic")
    monkeypatch.setattr(settings(), "gemini_model", "synthetic")
    with SessionLocal() as db:
        job = Job(
            owner_id=owner,
            kind="analysis",
            state="PROCESSING",
            lease_token="old",
            payload={"provider": "gemini", "consent": True},
        )
        db.add(job)
        db.commit()
        ident = job.id
    checkpoint = RequestCheckpoints(SessionLocal, ident, "old")
    budget = {"calls": 0, "tokens": 0, "max_calls": 1, "max_tokens": 500000}
    p = configured_provider(
        {
            "name": "gemini",
            "model": "synthetic",
            "key": "synthetic",
            "budget": budget,
            "checkpoint": checkpoint,
        }
    )
    _, _, payload = p.request("s", "p", analysis.CandidateBatch.model_json_schema())
    checkpoint.begin(
        payload,
        analysis.CandidateBatch.model_json_schema(),
        "candidate_generation",
        {"prompt_version": "evidence-v2.3.0"},
        5000,
        budget,
    )
    with pytest.raises(ProviderError, match="PROVIDER_CHECKPOINT_UNCERTAIN"):
        p.generate("s", "p", analysis.CandidateBatch, "candidate_generation")
    with SessionLocal() as db:
        db.get(Job, ident).state = "FAILED"
        db.commit()
    assert client.get(f"/api/v1/jobs/{ident}").json()["uncertain_ai_requests"] == 1
    assert client.post(f"/api/v1/jobs/{ident}/retry").status_code == 409
    assert (
        client.post(f"/api/v1/jobs/{ident}/retry", json={"acknowledge_uncertain_calls": True}).status_code
        == 200
    )
    with SessionLocal() as db:
        job = db.get(Job, ident)
        job.state = "PROCESSING"
        job.lease_token = "new"
        db.commit()
    p.checkpoint = RequestCheckpoints(SessionLocal, ident, "new")
    with pytest.raises(ProviderError, match="PROVIDER_OPERATION_BUDGET_EXCEEDED"):
        p.generate("s", "p", analysis.CandidateBatch, "candidate_generation")


def test_worker_resumes_completed_requests_after_failure_without_rebilling(client, monkeypatch):
    login_guest(client)
    monkeypatch.setattr(settings(), "gemini_api_key", "synthetic")
    monkeypatch.setattr(settings(), "gemini_model", "synthetic")
    source = upload_text(client, "Payment is due within thirty days.")
    original = httpx.Client
    requests = []

    def handler(request):
        requests.append(request)
        prompt = json.loads(request.content)["contents"][0]["parts"][0]["text"]
        if prompt.startswith("Extract"):
            p = json.loads(prompt[prompt.index("[") :])[0]
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
                        "rationale": "Stated",
                        "qualifications": [],
                        "cross_references": [],
                    }
                ]
            }
        else:
            result = {
                "support_status": "SUPPORTED",
                "rationale": "Stated",
                "missing_qualifiers": [],
                "unresolved_references": [],
            }
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(result)}]}}]
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    progress = worker.progress
    failed = []

    def interrupt(job, token, stage, *args, **kw):
        if stage == "AGGREGATING" and not failed:
            failed.append(True)
            raise RuntimeError("Synthetic restart after saved responses")
        return progress(job, token, stage, *args, **kw)

    monkeypatch.setattr(worker, "progress", interrupt)
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
    assert client.get(f"/api/v1/jobs/{submitted['job_id']}").json()["state"] == "FAILED"
    assert len(requests) == 2
    assert client.post(f"/api/v1/jobs/{submitted['job_id']}/retry").status_code == 200
    assert worker.run_once()
    assert len(requests) == 2
    assert client.get(f"/api/v1/jobs/{submitted['job_id']}").json()["state"] == "COMPLETED"


def test_compatible_truncation_uses_task_budget_and_cached_completed_retry(client, monkeypatch):
    login_guest(client)
    owner = client.get("/api/v1/me").json()["id"]
    with SessionLocal() as db:
        job = Job(owner_id=owner, kind="analysis", state="PROCESSING", lease_token="token")
        db.add(job)
        db.commit()
        ident = job.id
    original = httpx.Client
    sent = []

    def handler(request):
        payload = json.loads(request.content)
        sent.append(payload["max_tokens"])
        if len(sent) == 1:
            return httpx.Response(
                200, json={"choices": [{"finish_reason": "length", "message": {"content": "incomplete"}}]}
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "support_status": "SUPPORTED",
                                    "rationale": "Stated",
                                    "missing_qualifiers": [],
                                    "unresolved_references": [],
                                }
                            )
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: None)
    p = configured_provider(
        {
            "name": "groq",
            "model": "synthetic",
            "key": "synthetic",
            "checkpoint": RequestCheckpoints(SessionLocal, ident, "token"),
            "budget": {"calls": 0, "tokens": 0, "max_calls": 100, "max_tokens": 500000},
        }
    )
    p.generate("s", "p", analysis.Verdict, "semantic_verification")
    _, calls = p.generate("s", "p", analysis.Verdict, "semantic_verification")
    assert sent == [1024, 2048] and calls[0]["cached"]
