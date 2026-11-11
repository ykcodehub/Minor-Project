"""Synthetic provider fixtures are tests, never production fallback results."""

import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.providers.base import ProviderError, configured_provider, generate_with_fallback
from app.services import analysis
from app.services.analysis import CandidateBatch, Verdict, analyze, ask

SECTIONS = [
    {
        "id": "sec1",
        "source_id": "src1",
        "page": 1,
        "text": "We share data only with consent, except when required by law.",
    }
]
CHUNKS = [{"spans": [{"section_id": "sec1", "start": 0, "end": len(SECTIONS[0]["text"])}]}]


def candidate(**updates):
    return {
        "source_id": "src1",
        "section_id": "sec1",
        "category": "CONSENT",
        "statement": "The policy requires consent except when law requires sharing.",
        "rationale": "The clause states consent and its exception.",
        "quote": SECTIONS[0]["text"],
        "start": 0,
        "end": len(SECTIONS[0]["text"]),
        "page": 1,
        "qualifications": ["Legal-disclosure exception"],
        "cross_references": [],
        **updates,
    }


def install_model(monkeypatch, item=None, status="SUPPORTED", qualifiers=None):
    roles = []

    def generate(configs, system, prompt, schema, role):
        roles.append(role)
        call = {"provider": "test", "model": "fixture", "role": role}
        if schema is CandidateBatch:
            return CandidateBatch(findings=[candidate(**(item or {}))]), [call]
        return Verdict(
            support_status=status,
            rationale="Test rubric annotation.",
            missing_qualifiers=qualifiers or [],
            unresolved_references=[],
        ), [call]

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    return roles


def test_missing_provider_is_explicit_blocker():
    with pytest.raises(ProviderError, match="PROVIDER_NOT_CONFIGURED"):
        analyze(CHUNKS, SECTIONS, [])


def test_valid_source_requires_separate_semantic_review(monkeypatch):
    roles = install_model(monkeypatch)
    result = analyze(CHUNKS, SECTIONS, [{"name": "test"}])
    assert roles == ["candidate_generation", "semantic_verification"]
    finding = result["findings"][0]
    assert finding["support_status"] == "SUPPORTED"
    assert finding["citations"][0]["match_status"] == "EXACT"
    assert result["coverage"]["chunks_processed"] == 1


@pytest.mark.parametrize(
    "update",
    [{"page": 99}, {"quote": "Invented citation"}, {"source_id": "other"}, {"start": 9999, "end": 10000}],
)
def test_forged_citations_never_verified(monkeypatch, update):
    roles = install_model(monkeypatch, update)
    finding = analyze(CHUNKS, SECTIONS, [{"name": "test"}])["findings"][0]
    assert finding["support_status"] == "UNSUPPORTED"
    assert finding["citations"][0]["match_status"] == "INVALID"
    assert roles == ["candidate_generation"]


def test_quote_match_does_not_entail_statement(monkeypatch):
    install_model(monkeypatch, {"statement": "The company never shares data."}, status="UNSUPPORTED")
    finding = analyze(CHUNKS, SECTIONS, [{"name": "test"}])["findings"][0]
    assert finding["citations"][0]["match_status"] == "EXACT"
    assert finding["support_status"] == "UNSUPPORTED"


def test_missing_exception_downgrades_supported_verdict(monkeypatch):
    install_model(monkeypatch, qualifiers=["except when required by law"])
    finding = analyze(CHUNKS, SECTIONS, [{"name": "test"}])["findings"][0]
    assert finding["support_status"] == "PARTIALLY_SUPPORTED"


def test_semantic_failure_is_visible_ambiguous(monkeypatch):
    def generate(configs, system, prompt, schema, role):
        if schema is CandidateBatch:
            return CandidateBatch(findings=[candidate()]), [{"provider": "test", "model": "fixture"}]
        raise ProviderError("PROVIDER_RATE_LIMITED")

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    result = analyze(CHUNKS, SECTIONS, [{"name": "test"}])
    assert result["findings"][0]["support_status"] == "AMBIGUOUS"
    assert result["partial"]


def test_malformed_structured_candidates_fail_strictly():
    with pytest.raises(ValidationError):
        CandidateBatch.model_validate({"findings": [{**candidate(), "start": "0"}]})
    with pytest.raises(ValidationError):
        CandidateBatch.model_validate({"findings": [{**candidate(), "execute_shell": "rm -rf /"}]})


def test_no_supported_evidence_abstains_without_provider_call():
    response = ask("What is the retention period?", [], SECTIONS, [])
    assert response["answer"] == "I cannot confirm this from the available document."
    assert response["citations"] == []


@pytest.mark.parametrize("name", ["gemini", "groq", "openrouter"])
def test_adapters_normalize_structured_outputs(monkeypatch, name):
    requests = []
    original_client = httpx.Client
    output = {
        "support_status": "AMBIGUOUS",
        "rationale": "Insufficient context.",
        "missing_qualifiers": [],
        "unresolved_references": [],
    }

    def handler(request):
        requests.append(request)
        if name == "gemini":
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(output)}]}}
                    ],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs)
    )
    provider = configured_provider({"name": name, "model": "fixture", "key": "test-secret", "retries": 0})
    result, calls = provider.generate("system", "prompt", Verdict, "semantic_verification")
    assert result.support_status == "AMBIGUOUS"
    assert calls[0]["token_in"] == 10
    assert "test-secret" not in repr(provider)
    assert "test-secret" not in json.dumps(calls)
    payload = json.loads(requests[0].content)
    if name == "openrouter":
        assert payload["provider"]["allow_fallbacks"] is False


def test_retry_then_explicitly_permitted_fallback(monkeypatch):
    original_client = httpx.Client
    seen_hosts = []

    def handler(request):
        seen_hosts.append(request.url.host)
        if request.url.host == "api.groq.com":
            return httpx.Response(429, json={"error": {"message": "private body must not leak"}})
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"findings": []})}}]
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs)
    )
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: None)
    configs = [
        {"name": "groq", "model": "fixture", "key": "secret", "retries": 1},
        {"name": "openrouter", "model": "fixture", "key": "secret", "retries": 0},
    ]
    value, calls = generate_with_fallback(configs, "system", "prompt", CandidateBatch, "candidate_generation")
    assert value.findings == []
    assert seen_hosts == ["api.groq.com", "openrouter.ai"]  # quota errors fall back immediately
    assert calls[-1]["fallback"] is True
    assert calls[0]["outcome"] == "PROVIDER_RATE_LIMITED"
    assert "private body" not in json.dumps(calls)


def test_timeout_is_redacted(monkeypatch):
    original_client = httpx.Client

    def handler(request):
        raise httpx.ReadTimeout("private source and secret", request=request)

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs)
    )
    with pytest.raises(ProviderError, match="PROVIDER_TIMEOUT") as raised:
        configured_provider({"name": "groq", "model": "fixture", "key": "secret", "retries": 0}).generate(
            "system", "private source", Verdict, "semantic_verification"
        )
    assert "private source" not in str(raised.value)


def test_unconsented_provider_never_receives_fallback(monkeypatch):
    original_client = httpx.Client
    seen_hosts = []

    def handler(request):
        seen_hosts.append(request.url.host)
        return httpx.Response(503, text="unavailable")

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs)
    )
    with pytest.raises(ProviderError):
        generate_with_fallback(
            [{"name": "groq", "model": "fixture", "key": "secret", "retries": 0}],
            "system",
            "prompt",
            Verdict,
            "semantic_verification",
        )
    assert seen_hosts == ["api.groq.com"]


def test_partial_generation_reports_uncovered_chunks_and_sections(monkeypatch):
    calls = 0

    def generate(configs, system, prompt, schema, role):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ProviderError("PROVIDER_RATE_LIMITED")
        return CandidateBatch(findings=[]), [{"provider": "test", "model": "fixture"}]

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    midpoint = 20
    chunks = [
        {"spans": [{"section_id": "sec1", "start": 0, "end": midpoint}]},
        {"spans": [{"section_id": "sec1", "start": midpoint, "end": len(SECTIONS[0]["text"])}]},
    ]
    result = analyze(chunks, SECTIONS, [{"name": "test"}])
    assert result["partial"]
    assert result["coverage"]["chunks_processed"] == 1
    assert result["coverage"]["sections_processed"] == 0
    assert result["coverage"]["failed_chunks"] == [1]


def test_duplicate_findings_preserve_candidate_trace(monkeypatch):
    install_model(monkeypatch)
    result = analyze(CHUNKS + CHUNKS, SECTIONS, [{"name": "test"}])
    assert len(result["findings"]) == 1
    assert len(result["findings"][0]["candidate_ids"]) == 2


def test_question_answer_with_forged_citation_abstains(monkeypatch):
    finding = {
        "id": "f1",
        "statement": "Consent is required with a legal exception.",
        "support_status": "SUPPORTED",
        "citations": [{"match_status": "EXACT", "quote": SECTIONS[0]["text"]}],
    }

    def generate(configs, system, prompt, schema, role):
        return analysis.AnswerDraft(
            answer="Invented answer", cited_finding_ids=["other-user-finding"], abstain=False, limitations=[]
        ), []

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    result = ask("Can data be shared?", [finding], SECTIONS, [{"name": "test"}])
    assert result["citations"] == []
    assert result["answer"] == "I cannot confirm this from the available document."


def test_question_answer_requires_semantic_support(monkeypatch):
    finding = {
        "id": "f1",
        "statement": "Consent is required with a legal exception.",
        "support_status": "SUPPORTED",
        "original_candidate": candidate(),
        "citations": [{"match_status": "EXACT", "quote": SECTIONS[0]["text"]}],
    }

    def generate(configs, system, prompt, schema, role):
        if schema is analysis.AnswerDraft:
            return analysis.AnswerDraft(
                answer="They never share data.", cited_finding_ids=["f1"], abstain=False, limitations=[]
            ), []
        return Verdict(
            support_status="UNSUPPORTED",
            rationale="It omits a stated exception.",
            missing_qualifiers=[],
            unresolved_references=[],
        ), []

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    result = ask("Can data be shared?", [finding], SECTIONS, [{"name": "test"}])
    assert result["citations"] == []
    assert result["answer"] == "I cannot confirm this from the available document."


def test_invalid_provider_json_is_rejected(monkeypatch):
    original_client = httpx.Client

    def handler(request):
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "not JSON"}}]}
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs)
    )
    with pytest.raises(ProviderError, match="PROVIDER_INVALID_OUTPUT"):
        configured_provider({"name": "groq", "model": "fixture", "key": "secret", "retries": 0}).generate(
            "system", "prompt", Verdict, "semantic_verification"
        )


def test_semantic_review_receives_distant_exception(monkeypatch):
    fixture = json.loads((Path(__file__).parent / "fixtures" / "evidence_adversarial.json").read_text())[
        "cases"
    ][0]
    sections = fixture["sections"]
    first = sections[0]
    item = candidate(
        source_id=first["source_id"],
        section_id=first["id"],
        quote=first["text"],
        end=len(first["text"]),
        statement=fixture["claim"],
    )
    observed = []

    def generate(configs, system, prompt, schema, role):
        observed.append(prompt)
        if schema is CandidateBatch:
            return CandidateBatch(findings=[item]), [{"provider": "test", "model": "fixture"}]
        payload = json.loads(prompt[prompt.index("{") :])
        assert payload["whole_source_context"] is True
        assert "Notwithstanding" in payload["context"][2]["text"]
        return Verdict(
            support_status=fixture["expected"],
            rationale=fixture["reason"],
            missing_qualifiers=[],
            unresolved_references=[],
        ), [{"provider": "test", "model": "fixture"}]

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    chunks = [{"spans": [{"section_id": first["id"], "start": 0, "end": len(first["text"])}]}]
    result = analyze(chunks, sections, [{"name": "test"}])
    assert result["findings"][0]["support_status"] == "UNSUPPORTED"


def test_incomplete_global_context_never_gets_supported(monkeypatch):
    install_model(monkeypatch)
    sections = SECTIONS + [
        {"id": "large", "source_id": "src1", "page": 2, "text": "Other provision. " * 4000}
    ]
    result = analyze(CHUNKS, sections, [{"name": "test"}])
    assert result["findings"][0]["support_status"] == "AMBIGUOUS"
    assert result["partial"]
    assert "bounded context" in result["warnings"][0]
