"""Synthetic orchestration/security tests: never use live provider credentials."""

import json

import httpx
import pytest
from test_api import register, upload_text

from app.config import settings
from app.db import SessionLocal
from app.models import Job, User
from app.providers.base import ProviderError, configured_provider, generate_with_fallback
from app.services.analysis import CandidateBatch
from app.services.provider_policy import providers_for
from app.services.summary import summarize
from app.worker import run_once


def configured(monkeypatch):
    for name in ("gemini", "groq", "openrouter"):
        monkeypatch.setattr(settings(), name + "_api_key", "synthetic-key")
        monkeypatch.setattr(settings(), name + "_model", "synthetic-model")


def prefs(client, names):
    return client.patch(
        "/api/v1/me",
        json={"preferred_provider": "gemini", "retention_days": 30, "authorized_providers": names},
    )


def test_persistent_consent_submission_and_revocation(client, monkeypatch):
    register(client)
    configured(monkeypatch)
    assert prefs(client, ["gemini", "groq"]).status_code == 200
    assert client.get("/api/v1/me").json()["authorized_providers"] == ["gemini", "groq"]
    source = upload_text(client)
    submitted = client.post(
        "/api/v1/analyses", json={"source_ids": [source["source_id"]], "privacy_mode": "external"}
    )
    assert submitted.status_code == 202
    job_id = submitted.json()["job_id"]
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job.payload["provider"] == "gemini" and job.payload["fallback_providers"] == ["groq"]
    assert prefs(client, []).status_code == 200
    assert run_once()
    failed = client.get(f"/api/v1/jobs/{job_id}").json()
    assert failed["state"] == "FAILED" and "PROVIDER_PERMISSION_REVOKED" in failed["error"]
    assert client.post(f"/api/v1/jobs/{job_id}/retry").status_code == 403
    assert (
        client.post(
            "/api/v1/analyses",
            json={
                "source_ids": [source["source_id"]],
                "privacy_mode": "external",
                "provider": "openrouter",
                "consent": True,
            },
        ).status_code
        == 403
    )


def test_permission_rechecked_between_http_retries(client, monkeypatch):
    register(client)
    configured(monkeypatch)
    prefs(client, ["gemini"])
    user_id = client.get("/api/v1/me").json()["id"]
    with SessionLocal() as db:
        configs = providers_for(db.get(User, user_id), {"consent": True})
    requests = []
    original = httpx.Client

    def handler(request):
        requests.append(request)
        with SessionLocal() as db:
            db.get(User, user_id).authorized_providers = []
            db.commit()
        return httpx.Response(503)

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: None)
    with pytest.raises(ProviderError, match="PROVIDER_PERMISSION_REVOKED"):
        generate_with_fallback(configs, "system", "synthetic", CandidateBatch, "candidate_generation")
    assert len(requests) == 1


def test_413_falls_back_once_without_identical_retry(monkeypatch):
    seen = []
    original = httpx.Client

    def handler(request):
        seen.append(request.url.host)
        if request.url.host == "api.groq.com":
            return httpx.Response(413)
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"findings":[]}'}]}}]
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    configs = [{"name": name, "model": "synthetic-model", "key": "synthetic"} for name in ("groq", "gemini")]
    _, calls = generate_with_fallback(configs, "s", "synthetic", CandidateBatch, "candidate_generation")
    assert seen == ["api.groq.com", "generativelanguage.googleapis.com"]
    assert calls[0]["outcome"] == "PROVIDER_CONTEXT_LIMIT" and calls[1]["fallback"]


def test_serialized_schema_payload_budget_blocks_before_http(monkeypatch):
    def forbidden(*args, **kw):
        raise AssertionError("No network request allowed")

    monkeypatch.setattr(httpx.Client, "post", forbidden)
    config = {"name": "groq", "model": "synthetic-model", "key": "synthetic", "request_tokens": 1024}
    with pytest.raises(ProviderError, match="PROVIDER_CONTEXT_LIMIT") as raised:
        configured_provider(config).generate("s", "x " * 2000, CandidateBatch, "candidate_generation")
    assert raised.value.model_calls[0]["estimated_request_tokens"] > 1024


def test_operation_budget_caps_calls_across_tasks(monkeypatch):
    original = httpx.Client
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(503)

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: None)
    budget = {"calls": 0, "tokens": 0, "max_calls": 1, "max_tokens": 100000}
    configs = [
        {"name": name, "model": "synthetic-model", "key": "synthetic", "budget": budget}
        for name in ("gemini", "groq")
    ]
    with pytest.raises(ProviderError, match="PROVIDER_OPERATION_BUDGET_EXCEEDED"):
        generate_with_fallback(configs, "s", "synthetic", CandidateBatch, "candidate_generation")
    assert len(seen) == 1


@pytest.mark.parametrize("category", ["PRIVACY", "CONSENT", "TERMINATION", "DISPUTE", "CLAUSE", "OTHER"])
def test_summary_includes_previously_dropped_supported_categories(category):
    text = "The document states a synthetic term."
    section = {"id": "sec", "source_id": "src", "text": text, "page": 1}
    finding = {
        "id": "f",
        "finding_id": "f",
        "category": category,
        "support_status": "SUPPORTED",
        "qualifications": [],
        "citations": [
            {"source_id": "src", "section_id": "sec", "quote": text, "start": 0, "end": len(text), "page": 1}
        ],
    }
    coverage = {"chunks_total": 1, "chunks_processed": 1, "sections_total": 1, "sections_processed": 1}
    result = summarize([finding], [section], coverage, "COMPLETED")
    assert result["counts"]["verified"] == 1
    assert any(finding in group for group in result["groups"].values())
    finding["support_status"] = "AMBIGUOUS"
    partial = summarize([finding], [section], coverage, "PARTIAL_COMPLETION")
    assert partial["counts"]["verified"] == 0 and partial["counts"]["excluded"] == 1
    assert partial["level"] == "Not Determinable" and not partial["overview_findings"]


def test_small_context_model_audits_all_windows_before_supported(monkeypatch):
    from app.services import analysis

    sections = [
        {
            "id": "sec",
            "source_id": "src",
            "page": 1,
            "text": "Payment is due. " + "General procedural text. " * 800,
        }
    ]
    candidate = {
        "source_id": "src",
        "section_id": "sec",
        "quote": "Payment is due.",
        "page": 1,
        "start": 0,
        "end": 15,
        "category": "OBLIGATION",
        "statement": "Payment is due.",
        "rationale": "Stated",
        "qualifications": [],
        "cross_references": [],
    }
    roles = []

    def generate(configs, system, prompt, schema, role):
        roles.append(role)
        calls = [{"provider": "groq", "model": "synthetic", "role": role, "outcome": "SUCCESS"}]
        if schema is analysis.ContextAudit:
            return analysis.ContextAudit(relevant_passages=[], unresolved_context=False), calls
        return analysis.Verdict(
            support_status="SUPPORTED", rationale="Stated", missing_qualifiers=[], unresolved_references=[]
        ), calls

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    verdict, calls = analysis._review(
        candidate, sections, [{"name": "groq", "model": "synthetic", "key": "synthetic"}]
    )
    assert roles.count("context_verification") > 1
    assert verdict["support_status"] == "SUPPORTED" and verdict["context_complete"]
    assert "window audit" in verdict["context_review_method"]
    assert len(calls) == len(roles)


def test_failed_source_window_audit_cannot_be_promoted(monkeypatch):
    from app.services import analysis

    sections = [
        {
            "id": "sec",
            "source_id": "src",
            "page": 1,
            "text": "Payment is due. " + "General procedural text. " * 800,
        }
    ]
    candidate = {
        "source_id": "src",
        "section_id": "sec",
        "quote": "Payment is due.",
        "page": 1,
        "start": 0,
        "end": 15,
        "category": "OBLIGATION",
        "statement": "Payment is due.",
        "rationale": "Stated",
        "qualifications": [],
        "cross_references": [],
    }

    def generate(configs, system, prompt, schema, role):
        if schema is analysis.ContextAudit:
            return analysis.ContextAudit(relevant_passages=[], unresolved_context=True), [
                {"provider": "groq", "model": "synthetic", "role": role}
            ]
        return analysis.Verdict(
            support_status="SUPPORTED", rationale="Stated", missing_qualifiers=[], unresolved_references=[]
        ), [{"provider": "groq", "model": "synthetic", "role": role}]

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    verdict, _ = analysis._review(
        candidate, sections, [{"name": "groq", "model": "synthetic", "key": "synthetic"}]
    )
    assert verdict["support_status"] == "AMBIGUOUS" and not verdict["context_complete"]


def test_budget_override_cannot_replace_model_or_credentials():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite://", provider_limits={"groq": {"model": 123}})


def test_model_aware_rechunking_keeps_exact_source_offsets(monkeypatch):
    from app.services import analysis
    from app.services.chunking import chunk_sections

    section = {
        "id": "section",
        "source_id": "source",
        "page": 7,
        "text": "Payment must be made within thirty days. " * 1000,
    }
    mapped = []

    def generate(configs, system, prompt, schema, role):
        data = json.loads(prompt[prompt.index("[") :])
        mapped.extend(data)
        return analysis.CandidateBatch(findings=[]), [
            {"provider": "groq", "model": "synthetic", "outcome": "SUCCESS"}
        ]

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    result = analysis.analyze(
        chunk_sections([section]), [section], [{"name": "groq", "model": "synthetic", "key": "synthetic"}]
    )
    assert result["coverage"]["sections_processed"] == 1
    assert len(mapped) > 1
    assert all(
        p["text"] == section["text"][p["start_offset"] : p["end_offset"]]
        and p["page"] == 7
        and p["section_id"] in {"section", "r0"}
        for p in mapped
    )


def test_worker_fallback_verification_persistence_and_summary(client, monkeypatch):
    register(client)
    configured(monkeypatch)
    prefs(client, ["gemini", "groq"])
    source = upload_text(client, "Payment must be made within thirty days.")
    original = httpx.Client
    seen = []

    def handler(request):
        seen.append(request.url.host)
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(503)
        prompt = json.loads(request.content)["messages"][1]["content"]
        if prompt.startswith("Extract"):
            passage = json.loads(prompt[prompt.index("[") :])[0]
            result = {
                "findings": [
                    {
                        "source_id": passage["source_id"],
                        "section_id": passage["section_id"],
                        "quote": passage["text"],
                        "start": passage["start_offset"],
                        "end": passage["end_offset"],
                        "page": passage["page"],
                        "category": "OBLIGATION",
                        "statement": "Payment must be made within thirty days.",
                        "rationale": "The source states the payment deadline.",
                        "qualifications": [],
                        "cross_references": [],
                    }
                ]
            }
        else:
            result = {
                "support_status": "SUPPORTED",
                "rationale": "Entailed by the supplied complete source.",
                "missing_qualifiers": [],
                "unresolved_references": [],
            }
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: None)
    response = client.post(
        "/api/v1/analyses", json={"source_ids": [source["source_id"]], "privacy_mode": "external"}
    )
    assert response.status_code == 202
    assert run_once()
    ident = response.json()["analysis_id"]
    assert client.get(f"/api/v1/jobs/{response.json()['job_id']}").json()["state"] == "COMPLETED"
    summary = client.get(f"/api/v1/analyses/{ident}/summary").json()["summary"]
    assert summary["counts"]["verified"] == 1
    assert (
        summary["groups"]["obligations"][0]["citations"][0]["quote"]
        == "Payment must be made within thirty days."
    )
    assert seen.count("generativelanguage.googleapis.com") == 3 and seen.count("api.groq.com") == 2
