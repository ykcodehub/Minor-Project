"""Synthetic capability, reasoning and outage regressions; no real inference."""

import json
from datetime import timedelta

import httpx
import pytest

from app.db import SessionLocal
from app.models import now
from app.providers import model_policy
from app.providers.base import ProviderError, configured_provider, generate_with_fallback
from app.services.analysis import CandidateBatch
from app.services.provider_quota import hooks

REAL_MODEL_INFO = model_policy.model_info
REAL_ELIGIBLE_ENDPOINT = model_policy.eligible_endpoint
ORIGINAL_CLIENT = httpx.Client


@pytest.mark.parametrize(
    "status,price,expected",
    [
        (-5, "0", "PROVIDER_NO_HEALTHY_ENDPOINT"),
        (0, "0.01", "PROVIDER_NO_HEALTHY_ENDPOINT"),
        (0, "0", None),
    ],
)
def test_real_endpoint_gate_blocks_unavailable_and_nonzero_pricing(monkeypatch, status, price, expected):
    monkeypatch.setattr(model_policy, "eligible_endpoint", REAL_ELIGIBLE_ENDPOINT)
    monkeypatch.setattr(model_policy, "_endpoint_cache", {})
    seen = []

    def handle(request):
        seen.append(request)
        assert request.method == "GET" and "authorization" not in request.headers
        return httpx.Response(
            200,
            json={
                "data": {
                    "endpoints": [
                        {
                            "tag": "synthetic",
                            "status": status,
                            "pricing": {"prompt": price, "completion": price},
                            "supported_parameters": [
                                "structured_outputs",
                                "max_tokens",
                                "response_format",
                                "reasoning",
                            ],
                        }
                    ]
                }
            },
        )

    transport(monkeypatch, handle)
    if expected:
        with pytest.raises(ProviderError, match=expected):
            model_policy.eligible_endpoint("test/structured:free")
    else:
        assert model_policy.eligible_endpoint("test/structured:free")["tag"] == "synthetic"
        assert model_policy.eligible_endpoint("test/structured:free")["tag"] == "synthetic"
    assert len(seen) == 1


def test_free_request_pins_endpoint_and_sets_zero_price_ceiling():
    p = configured_provider(config())
    _, _, payload = p.request("s", "p", CandidateBatch.model_json_schema())
    model_policy.apply_policy(p, payload)
    assert payload["provider"]["only"] == ["synthetic"]
    assert payload["provider"]["max_price"] == {"prompt": 0, "completion": 0, "request": 0}


def test_controlled_run_disables_output_recovery_without_weakening_validation(monkeypatch):
    from app.services import analysis
    from app.services.chunking import chunk_sections

    sections = [{"id": "r", "source_id": "s", "page": 1, "text": "Payment is due. " * 60}]
    seen = []

    def fail(*args):
        seen.append(args)
        raise ProviderError("PROVIDER_INVALID_OUTPUT")

    monkeypatch.setattr(analysis, "generate_with_fallback", fail)
    monkeypatch.setattr(analysis, "_split_source_chunk", lambda *args: pytest.fail("No recovery authorized"))
    with pytest.raises(ProviderError, match="ANALYSIS_GENERATION_FAILED"):
        analysis.analyze(
            chunk_sections(sections), sections, [{"name": "fixture", "no_output_recovery": True}]
        )
    assert len(seen) == 1


def test_invalid_index_offsets_stay_invalid_and_failure_is_shared_across_roles(monkeypatch):
    from app.services import analysis
    from app.services.context_index import SourceWideIndex

    quote = "Data is shared only with consent."
    text = "Routine administrative process. " * 150 + quote
    sections = [{"id": "original", "source_id": "s", "page": 1, "text": text}]
    seen = []

    def generate(configs, system, prompt, schema, role):
        seen.append(role)
        assert "Set start and end to null" in prompt
        return analysis.ContextAudit(
            relevant_passages=[
                {
                    "source_id": "s0",
                    "section_id": "r0",
                    "page": 1,
                    "quote": quote,
                    "start": text.index(quote),
                    "end": len(text) - 1,
                }
            ],
            unresolved_context=False,
        ), []

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    cfg = {"name": "groq", "model": "synthetic", "key": "synthetic", "budget": {"calls": 0}}
    for _ in range(2):
        record, _ = SourceWideIndex(sections).prepare("s", cfg)
        assert not record["complete"] and record["error"] == "PROVIDER_INVALID_OUTPUT"
    assert seen == ["context_indexing"]


def transport(monkeypatch, handler):
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: ORIGINAL_CLIENT(transport=httpx.MockTransport(handler), **kw)
    )
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: None)


def config(**extra):
    return {"name": "openrouter", "model": "test/structured:free", "key": "synthetic", **extra}


@pytest.mark.parametrize("model", ["openrouter/free", "openrouter/auto", "@private/router"])
def test_dynamic_routers_rejected_without_inference(monkeypatch, model):
    transport(monkeypatch, lambda request: pytest.fail("Router must not receive content"))
    with pytest.raises(ProviderError, match="PROVIDER_EXPLICIT_MODEL_REQUIRED") as error:
        configured_provider(config(model=model)).generate("s", "p", CandidateBatch, "candidate_generation")
    assert not error.value.model_calls[0].get("request_sent")


@pytest.mark.parametrize(
    "role",
    [
        "candidate_generation",
        "context_indexing",
        "semantic_verification",
        "explanation_translation",
        "translation_verification",
        "question_answering",
    ],
)
def test_each_role_disables_optional_reasoning_and_accounts_full_payload(monkeypatch, role):
    def handle(request):
        payload = json.loads(request.content)
        assert payload["reasoning"] == {"enabled": False}
        assert payload["provider"]["allow_fallbacks"] is False
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": '{"findings":[]}'}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )

    transport(monkeypatch, handle)
    _, calls = configured_provider(config()).generate("s", "p", CandidateBatch, role)
    call = calls[0]
    assert call["estimated_request_tokens"] == call["estimated_input_tokens"] + call["reserved_output_tokens"]
    assert call["role"] == role and call["token_out"] == 5


def test_mandatory_reasoning_rejected_before_billing(monkeypatch):
    monkeypatch.setattr(
        model_policy,
        "model_info",
        lambda model: {
            "supported_parameters": ["structured_outputs", "max_tokens", "reasoning"],
            "reasoning": {"mandatory": True, "supported_efforts": ["high"]},
        },
    )
    transport(monkeypatch, lambda request: pytest.fail("Incompatible model must not receive content"))
    with pytest.raises(ProviderError, match="PROVIDER_REASONING_INCOMPATIBLE"):
        configured_provider(config()).generate("s", "p", CandidateBatch, "semantic_verification")


def test_actual_model_limits_tighten_local_budget(monkeypatch):
    monkeypatch.setattr(
        model_policy,
        "model_info",
        lambda model: {
            "supported_parameters": ["structured_outputs", "max_tokens"],
            "context_length": 2000,
            "top_provider": {"max_completion_tokens": 100},
        },
    )
    p = configured_provider(config())
    payload = {"max_tokens": 4096, "provider": {}}
    model_policy.apply_policy(p, payload)
    assert p.request_tokens == p.context_tokens == 2000 and payload["max_tokens"] == 100
    assert p.max_output_tokens == 100


@pytest.mark.parametrize(
    "model,control",
    [
        ("gemini-3.6-flash", {"thinkingLevel": "low"}),
        ("gemini-2.5-flash", {"thinkingBudget": 0}),
    ],
)
def test_gemini_controls_are_model_specific(model, control):
    p = configured_provider({"name": "gemini", "model": model, "key": "synthetic"})
    _, _, payload = p.request("s", "p", CandidateBatch.model_json_schema())
    model_policy.apply_policy(p, payload)
    assert payload["generationConfig"]["thinkingConfig"] == control


def test_openai_uses_the_compatible_chat_completions_contract():
    provider = configured_provider({"name": "openai", "model": "gpt-4o-mini", "key": "synthetic"})
    url, headers, payload = provider.request("system", "prompt", CandidateBatch.model_json_schema())
    assert url == "https://api.openai.com/v1/chat/completions"
    assert headers == {"Authorization": "Bearer synthetic"}
    assert payload["model"] == "gpt-4o-mini"
    assert payload["response_format"]["type"] == "json_schema"


def test_rejected_reasoning_control_never_retries_with_reasoning_enabled(monkeypatch):
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"param": "reasoning", "message": "Unsupported reasoning"}})

    transport(monkeypatch, handle)
    with pytest.raises(ProviderError, match="PROVIDER_REASONING_INCOMPATIBLE"):
        configured_provider(config()).generate("s", "p", CandidateBatch, "candidate_generation")
    assert len(seen) == 1 and seen[0]["reasoning"] == {"enabled": False}


def test_gemini_reasoning_exhaustion_does_not_grow_or_repeat_output(monkeypatch):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "MAX_TOKENS"}],
                "usageMetadata": {"thoughtsTokenCount": 4096, "candidatesTokenCount": 0},
            },
        )

    transport(monkeypatch, handle)
    with pytest.raises(ProviderError, match="PROVIDER_REASONING_EXHAUSTED"):
        configured_provider({"name": "gemini", "model": "gemini-3.6-flash", "key": "synthetic"}).generate(
            "s", "p", CandidateBatch, "candidate_generation"
        )
    assert len(seen) == 1


def test_catalog_cached_and_outage_fails_closed(monkeypatch):
    monkeypatch.setattr(model_policy, "model_info", REAL_MODEL_INFO)
    monkeypatch.setattr(model_policy, "_cache", {})
    seen = []

    def handle(request):
        seen.append(request)
        assert request.method == "GET" and "authorization" not in request.headers
        return httpx.Response(503)

    transport(monkeypatch, handle)
    for _ in range(2):
        with pytest.raises(ProviderError, match="PROVIDER_CAPABILITIES_UNAVAILABLE"):
            model_policy.model_info("test/structured:free")
    assert len(seen) == 1


def test_reasoning_exhaustion_never_repeats_or_subdivides_candidate(monkeypatch):
    from app.services import analysis
    from app.services.chunking import chunk_sections

    seen = []

    def handle(request):
        payload = json.loads(request.content)
        seen.append(payload)
        limit = payload["max_tokens"]
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "length", "message": {"content": ""}}],
                "usage": {
                    "completion_tokens": limit,
                    "completion_tokens_details": {"reasoning_tokens": limit},
                },
            },
        )

    transport(monkeypatch, handle)
    sections = [{"id": "r", "source_id": "s", "page": 1, "text": "Payment is due. " * 100}]
    budget = {"calls": 0, "tokens": 0, "max_calls": 5, "max_tokens": 50000}
    with pytest.raises(ProviderError, match="ANALYSIS_GENERATION_FAILED") as error:
        analysis.analyze(chunk_sections(sections), sections, [config(budget=budget)])
    assert len(seen) == 1
    assert error.value.model_calls[0]["outcome"] == "PROVIDER_REASONING_EXHAUSTED"
    assert ("openrouter", "candidate_generation") in budget["exhausted_reasoning_tasks"]


def test_incompatible_primary_falls_back_only_to_authorized_list(monkeypatch):
    seen = []

    def handle(request):
        seen.append(request.url.host)
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": '{"findings":[]}'}}],
            },
        )

    transport(monkeypatch, handle)
    _, calls = generate_with_fallback(
        [
            config(model="openrouter/free"),
            {"name": "groq", "model": "openai/gpt-oss-20b", "key": "synthetic"},
        ],
        "s",
        "p",
        CandidateBatch,
        "candidate_generation",
    )
    assert seen == ["api.groq.com"]
    assert calls[0]["outcome"] == "PROVIDER_EXPLICIT_MODEL_REQUIRED" and calls[-1]["fallback"]


def test_503_exhaustion_shared_outage_expires_without_touching_quota(client, monkeypatch):
    from app.services import provider_quota

    current = now()
    monkeypatch.setattr(provider_quota, "now", lambda: current)
    cfg = {"name": "gemini", "model": "synthetic", "key": "synthetic"}
    check, block = hooks(cfg, SessionLocal, category="outage")
    quota_check, _ = hooks(cfg, SessionLocal)
    cfg.update(outage_check=check, outage_block=block)
    seen = []
    transport(monkeypatch, lambda request: seen.append(request) or httpx.Response(503))
    with pytest.raises(ProviderError, match="PROVIDER_UNAVAILABLE"):
        configured_provider(cfg).generate("s", "p", CandidateBatch, "candidate_generation")
    assert len(seen) == 3 and check() == 30 and quota_check() == 0
    with pytest.raises(ProviderError, match="PROVIDER_TEMPORARILY_SUPPRESSED"):
        configured_provider(cfg).generate("s", "different", CandidateBatch, "question_answering")
    assert len(seen) == 3
    current += timedelta(seconds=31)
    assert check() == 0


def test_outage_never_blocks_reuse_of_completed_checkpoint(client, monkeypatch):
    # Existing quota/checkpoint regressions cover the same before_reserve boundary.
    from conftest import login_guest

    from app.models import Job
    from app.services.checkpoints import RequestCheckpoints

    owner = login_guest(client)["id"]
    with SessionLocal() as db:
        job = Job(owner_id=owner, kind="analysis", state="PROCESSING", lease_token="test")
        db.add(job)
        db.commit()
        ident = job.id
    paused = False
    cfg = config(
        checkpoint=RequestCheckpoints(SessionLocal, ident, "test"),
        outage_check=lambda: paused,
        budget={"calls": 0, "tokens": 0, "max_calls": 5, "max_tokens": 50000},
    )
    seen = []
    transport(
        monkeypatch,
        lambda request: (
            seen.append(request)
            or httpx.Response(
                200,
                json={
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"findings":[]}'}}],
                },
            )
        ),
    )
    provider = configured_provider(cfg)
    provider.generate("s", "p", CandidateBatch, "candidate_generation")
    paused = True
    _, calls = provider.generate("s", "p", CandidateBatch, "candidate_generation")
    assert len(seen) == 1 and calls[0]["cached"]
