"""Full-envelope budgeting regressions. Only synthetic sources and mocked HTTP."""

import json
import uuid

import httpx
import pytest

from app.providers.base import ProviderError, configured_provider
from app.services import analysis
from app.services.chunking import chunk_sections
from app.services.context_index import compact_passages


def sources():
    return [
        {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"synthetic-section-{i}")),
            "source_id": "synthetic-source-1234567890",
            "page": i // 20 + 1,
            "heading": f"Section {i}",
            "text": f"Clause {i}: Payment is due within thirty days, subject to the stated exceptions.",
        }
        for i in range(345)
    ]


def test_many_short_sections_are_split_by_full_wire_cost(monkeypatch):
    sections = sources()
    configs = [{"name": "openrouter", "model": "test/structured:free", "key": "synthetic"}]
    provider = configured_provider(configs[0])
    raw = chunk_sections(sections)
    assert any(
        not provider.fits(
            analysis.SYSTEM,
            analysis._candidate_prompt(analysis._mapped_passages([c], sections)),
            analysis.CandidateBatch.model_json_schema(),
        )
        for c in raw
    )
    fitted = analysis._fit_candidate_chunks(raw, sections, configs)
    assert len(fitted) >= len(raw)
    covered = {s["id"]: set() for s in sections}
    for chunk in fitted:
        passages = analysis._mapped_passages([chunk], sections)
        assert provider.fits(
            analysis.SYSTEM, analysis._candidate_prompt(compact_passages(passages)[0]), analysis.CandidateBatch.model_json_schema()
        )
        for passage in passages:
            original = next(s for s in sections if s["id"] == passage["section_id"])
            assert passage["page"] == original["page"]
            assert passage["text"] == original["text"][passage["start_offset"] : passage["end_offset"]]
            covered[original["id"]].update(range(passage["start_offset"], passage["end_offset"]))
    assert all(len(covered[s["id"]]) == len(s["text"]) for s in sections)
    original_client = httpx.Client
    sent = []

    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "test/structured:free"
        assert provider.request_usage(payload)["estimated_request_tokens"] <= 12000
        sent.append(payload)
        return httpx.Response(
            200,
            json={
                "model": "test/structured:free",
                "choices": [{"finish_reason": "stop", "message": {"content": '{"findings":[]}'}}],
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(handler), **kw)
    )
    result = analysis.analyze(raw, sections, configs)
    assert result["coverage"]["sections_processed"] == len(sections)
    assert len(sent) == result["coverage"]["chunks_processed"]
    assert all(c["response_model"] == "test/structured:free" for c in result["model_calls"])


def test_free_router_has_policy_cap_not_invented_selected_context():
    p = configured_provider({"name": "openrouter", "model": "openrouter/free", "key": "synthetic"})
    _, _, payload = p.request("system", "prompt", analysis.CandidateBatch.model_json_schema())
    usage = p.request_usage(payload)
    assert usage["context_tokens"] is None and usage["budget_basis"] == "router_application_policy"
    assert usage["reserved_output_tokens"] == 4096 and usage["request_token_limit"] == 12000
    assert usage["estimated_request_tokens"] == usage["estimated_input_tokens"] + 4096


def test_model_id_override_and_namespace_precedence():
    from app.config import Settings

    cfg = Settings(
        _env_file=None,
        environment="development",
        database_url="postgresql+psycopg://synthetic:placeholder@invalid.example/veriora",
        openrouter_model="test/structured:free",
        provider_limits={
            "openrouter": {"request_tokens": 12000},
            "test/structured:free": {"context_tokens": 9000},
            "openrouter/test/structured:free": {"max_output_tokens": 2048},
        },
    )
    configured = next(c for c in cfg.providers() if c["name"] == "openrouter")
    p = configured_provider(configured)
    assert p.request_tokens == 9000 and p.max_output_tokens == 2048


def test_small_explicit_limits_are_not_silently_increased(monkeypatch):
    p = configured_provider(
        {
            "name": "openrouter",
            "model": "vendor/model",
            "key": "synthetic",
            "context_tokens": 512,
            "max_output_tokens": 64,
            "max_payload_bytes": 1024,
        }
    )
    assert p.request_tokens == 512 and p.max_output_tokens == 64 and p.max_payload_bytes == 1024

    def forbidden(*a, **kw):
        raise AssertionError("must not send oversized request")

    monkeypatch.setattr(httpx.Client, "post", forbidden)
    with pytest.raises(ProviderError, match="PROVIDER_CONTEXT_LIMIT") as error:
        p.generate("s", "p", analysis.CandidateBatch, "candidate_generation")
    assert (
        len(error.value.model_calls) == 1 and error.value.model_calls[0]["budget_phase"] == "local_preflight"
    )


def test_upstream_context_rejection_is_not_blindly_retried(monkeypatch, caplog):
    original = httpx.Client
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(
            400, json={"error": {"message": "Maximum context length exceeded. PRIVATE SOURCE MUST NOT LEAK"}}
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(ProviderError, match="PROVIDER_CONTEXT_LIMIT") as error:
        configured_provider({"name": "openrouter", "model": "test/structured:free", "key": "synthetic"}).generate(
            "s", "p", analysis.CandidateBatch, "candidate_generation"
        )
    assert len(sent) == 1 and error.value.model_calls[0]["budget_phase"] == "provider_response"
    assert "PRIVATE SOURCE" not in caplog.text


def test_context_windows_also_fit_full_schema_and_metadata(monkeypatch):
    sections = sources()[:200]
    first = sections[0]
    candidate = {
        "source_id": first["source_id"],
        "section_id": first["id"],
        "page": first["page"],
        "quote": first["text"],
        "start": 0,
        "end": len(first["text"]),
        "category": "CLAUSE",
        "statement": first["text"],
        "rationale": "Stated text",
        "qualifications": [],
        "cross_references": [],
    }
    config = {"name": "openrouter", "model": "test/structured:free", "key": "synthetic"}
    provider = configured_provider(config)
    roles = []

    def generate(configs, system, prompt, schema, role):
        assert provider.fits(system, prompt, schema.model_json_schema())
        roles.append(role)
        calls = [{"provider": "openrouter", "model": "test/structured:free", "outcome": "SUCCESS"}]
        if schema is analysis.ContextAudit:
            return analysis.ContextAudit(relevant_passages=[], unresolved_context=False), calls
        return analysis.Verdict(
            support_status="SUPPORTED",
            rationale="Supplied text matches.",
            missing_qualifiers=[],
            unresolved_references=[],
        ), calls

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    verdict, _ = analysis._review(candidate, sections, [config])
    assert verdict["support_status"] == "SUPPORTED"
    assert 1 < roles.count("context_verification") <= 12


def test_persisted_permissions_allow_context_fallback_not_unchecked_provider(client, monkeypatch):
    from test_api import register, upload_text

    from app.config import settings
    from app.worker import run_once

    register(client)
    for name in ("gemini", "groq", "openrouter"):
        monkeypatch.setattr(settings(), name + "_api_key", "synthetic")
        monkeypatch.setattr(
            settings(), name + "_model", "test/structured:free" if name == "openrouter" else "synthetic-model"
        )
    response = client.patch(
        "/api/v1/me",
        json={
            "preferred_provider": "openrouter",
            "retention_days": 30,
            "authorized_providers": ["openrouter", "groq"],
        },
    )
    assert response.status_code == 200
    source = upload_text(client)
    original = httpx.Client
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "openrouter.ai":
            return httpx.Response(400, json={"error": {"code": "context_length_exceeded"}})
        assert request.url.host == "api.groq.com"
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"findings":[]}'}}]}
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    submitted = client.post(
        "/api/v1/analyses", json={"source_ids": [source["source_id"]], "privacy_mode": "external"}
    )
    assert submitted.status_code == 202 and run_once()
    assert hosts == ["openrouter.ai", "api.groq.com"]
    result = client.get(f"/api/v1/analyses/{submitted.json()['analysis_id']}").json()
    assert result["status"] == "COMPLETED"
    assert result["model_calls"][0]["outcome"] == "PROVIDER_CONTEXT_LIMIT"
    assert result["model_calls"][1]["fallback"]
