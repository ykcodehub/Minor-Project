"""Recorded-response diagnosis and controlled semantic regressions, never inference."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.providers.base import ProviderError, ordered_configs
from app.services import analysis as a
from app.services.context_index import SourceWideIndex

ROOT = Path(__file__).resolve().parents[2]


def candidate(text="Invoices must be paid within thirty days.", category="PAYMENT"):
    return {
        "source_id": "s",
        "section_id": "r",
        "page": 1,
        "quote": text,
        "statement": text,
        "category": category,
        "qualifications": [],
        "cross_references": [],
    }


def verdict(status="SUPPORTED", **extra):
    return a.Verdict(
        support_status=status,
        rationale="Controlled source-only evaluation.",
        missing_qualifiers=[],
        unresolved_references=[],
        category_consistent=True,
        **extra,
    )


def test_verifier_receives_category_without_generation_rationale():
    claim = candidate(category="RIGHT")
    claim["rationale"] = "Untrusted candidate rationale"
    prompt = a._verification_prompt(claim, [{"id": "r", "source_id": "s", "text": claim["quote"]}], True)
    payload = json.loads(prompt[prompt.index("{") :])
    assert payload["candidate"]["category"] == "RIGHT"
    assert "rationale" not in payload["candidate"]
    assert "not legal enforceability" in prompt


def test_recorded_fabricated_references_are_rejected_not_promoted(monkeypatch):
    recorded = json.loads((ROOT / "docs/benchmarks/college_live_compact.json").read_text())["findings"][1]
    old = recorded["verification"]
    response = a.Verdict(
        **{k: old[k] for k in ("support_status", "rationale", "missing_qualifiers", "unresolved_references")}
    )
    monkeypatch.setattr(a, "generate_with_fallback", lambda *args: (response, [{"provider": "openrouter"}]))
    context = [{"id": "r", "source_id": "s", "text": recorded["citations"][0]["quote"]}]
    with pytest.raises(ProviderError, match="PROVIDER_VERDICT_UNGROUNDED"):
        a._review_context(candidate(context[0]["text"], "RESTRICTION"), context, [], context, True, [])
    assert recorded["support_status"] == "PARTIALLY_SUPPORTED"


@pytest.mark.parametrize("status", ["SUPPORTED", "AMBIGUOUS", "UNSUPPORTED", "PARTIALLY_SUPPORTED"])
def test_actual_source_grounded_decisions_are_never_upgraded(monkeypatch, status):
    response = verdict(status)
    monkeypatch.setattr(a, "generate_with_fallback", lambda *args: (response, []))
    claim = candidate()
    context = [{"id": "r", "source_id": "s", "text": claim["quote"]}]
    result, _ = a._review_context(claim, context, [], context, True, [])
    assert result["support_status"] == status and result["category_reviewed"]


def test_category_mismatch_cannot_produce_supported_finding(monkeypatch):
    response = a.Verdict(
        support_status="SUPPORTED",
        rationale="Quote is entailed but not a customer right.",
        missing_qualifiers=[],
        unresolved_references=[],
        category_consistent=False,
    )
    monkeypatch.setattr(a, "generate_with_fallback", lambda *args: (response, []))
    claim = candidate("The customer grants an irrevocable license to submitted materials.", "RIGHT")
    context = [{"id": "r", "source_id": "s", "text": claim["quote"]}]
    with pytest.raises(ProviderError, match="PROVIDER_CATEGORY_MISMATCH"):
        a._review_context(claim, context, [], context, True, [])


def test_source_locator_in_rationale_is_not_a_fabricated_legal_reference(monkeypatch):
    response = a.Verdict(
        support_status="SUPPORTED",
        rationale="Section sec_abc_3 states the deadline.",
        missing_qualifiers=[],
        unresolved_references=[],
        category_consistent=True,
    )
    monkeypatch.setattr(a, "generate_with_fallback", lambda *args: (response, []))
    claim = candidate()
    context = [{"id": "r", "source_id": "s", "text": claim["quote"]}]
    result, _ = a._review_context(claim, context, [], context, True, [])
    assert result["support_status"] == "SUPPORTED"


def test_question_answer_review_does_not_apply_a_nonexistent_finding_category(monkeypatch):
    response = a.Verdict(
        support_status="SUPPORTED",
        rationale="Answer follows source wording.",
        missing_qualifiers=[],
        unresolved_references=[],
        category_consistent=False,
    )
    monkeypatch.setattr(a, "generate_with_fallback", lambda *args: (response, []))
    claim = candidate()
    claim.pop("category")
    context = [{"id": "r", "source_id": "s", "text": claim["quote"]}]
    result, _ = a._review_context(claim, context, [], context, True, [])
    assert result["support_status"] == "SUPPORTED" and not result["category_reviewed"]


def test_task_priority_only_reorders_caller_authorized_providers():
    configs = [
        {"name": "gemini", "task_priority": {"candidate_generation": 0}},
        {"name": "groq", "task_priority": {"semantic_verification": 0}},
    ]
    assert [c["name"] for c in ordered_configs(configs, "candidate_generation")] == ["gemini", "groq"]
    assert [c["name"] for c in ordered_configs(configs, "semantic_verification")] == ["groq", "gemini"]
    assert [c["name"] for c in ordered_configs(configs[:1], "semantic_verification")] == ["gemini"]
    from app.services.provider_policy import names_for

    assert (
        names_for(SimpleNamespace(authorized_providers=[], preferred_provider="groq"), {"consent": True})
        == []
    )


def test_task_routing_configuration_is_validated():
    kwargs = {"_env_file": None, "database_url": "sqlite://", "environment": "test"}
    cfg = Settings(**kwargs, ai_task_provider_order={"semantic_verification": ["groq", "gemini"]})
    assert cfg.ai_task_provider_order["semantic_verification"] == ["groq", "gemini"]
    for value in ({"invented_role": ["groq"]}, {"semantic_verification": ["groq", "groq"]}):
        with pytest.raises(ValueError):
            Settings(**kwargs, ai_task_provider_order=value)


def test_indexing_and_semantics_can_use_different_authorized_providers(monkeypatch):
    quote = "Invoices must be paid within thirty days."
    section = {"id": "r", "source_id": "s", "page": 1, "text": quote + " Routine wording." * 900}
    configs = [
        {
            "name": "gemini",
            "key": "synthetic",
            "model": "synthetic",
            "task_priority": {"context_indexing": 0},
        },
        {
            "name": "groq",
            "key": "synthetic",
            "model": "synthetic",
            "task_priority": {"semantic_verification": 0},
        },
    ]
    stages = []

    def prepare(self, source_id, config):
        stages.append(("index", config["name"]))
        return {
            "complete": True,
            "excerpts": [],
            "windows_total": 1,
            "windows_processed": 1,
            "error": None,
        }, []

    def review(claim, sections, providers, context, complete, calls_before):
        stages.append(("review", providers[0]["name"]))
        return {"support_status": "SUPPORTED", "rationale": "Controlled", "context_complete": True}, []

    monkeypatch.setattr(SourceWideIndex, "prepare", prepare)
    monkeypatch.setattr(a, "_review_context", review)
    result, _ = SourceWideIndex([section]).review(candidate(), configs)
    assert stages == [("index", "gemini"), ("review", "groq")]
    assert result["source_index"]["provider"] == "gemini"


def test_invalid_verdict_falls_back_to_another_authorized_reviewer(monkeypatch):
    section = {"id": "r", "source_id": "s", "page": 1, "text": candidate()["quote"]}
    seen = []

    def generate(configs, system, prompt, schema, role):
        name = configs[0]["name"]
        seen.append(name)
        if name == "openrouter":
            return a.Verdict(
                support_status="AMBIGUOUS",
                rationale="Missing sec_abc_3.",
                missing_qualifiers=[],
                unresolved_references=["sec_abc_3"],
            ), [{"provider": name}]
        return verdict(), [{"provider": name}]

    monkeypatch.setattr(a, "generate_with_fallback", generate)
    configs = [{"name": n, "key": "synthetic", "model": "synthetic"} for n in ("openrouter", "groq")]
    result, _ = SourceWideIndex([section]).review(candidate(), configs)
    assert result["support_status"] == "SUPPORTED" and seen == ["openrouter", "groq"]


@pytest.mark.parametrize("negative,expected_supported", [(False, 7), (True, 3)])
def test_two_page_fixture_keeps_positive_negative_and_unsupported_findings_separate(
    monkeypatch, negative, expected_supported
):
    from test_risk_dashboard import CLAUSES, agreement_pdf

    from app.services.chunking import chunk_sections
    from app.services.ingest import extract
    from app.services.summary import summarize

    sections = extract(agreement_pdf(), "synthetic.pdf")["sections"]
    for section in sections:
        section["source_id"] = "synthetic-source"

    def generate(configs, system, prompt, schema, role):
        call = [{"provider": "groq", "model": "synthetic", "outcome": "SUCCESS"}]
        if role == "candidate_generation":
            entries = []
            for passage in json.loads(prompt[prompt.index("[") :]):
                for category, quote in CLAUSES:
                    if quote in passage["text"]:
                        statement = quote
                        if negative and category == "PAYMENT":
                            statement = "Invoices need not be paid."
                        if negative and category == "PRIVACY":
                            statement = "Data is shared without consent."
                        entries.append(
                            {
                                "source_id": passage["source_id"],
                                "section_id": passage["section_id"],
                                "page": passage["page"],
                                "start": None,
                                "end": None,
                                "quote": quote,
                                "category": "RIGHT" if negative and category == "RESTRICTION" else category,
                                "statement": statement,
                                "rationale": "Controlled fixture",
                                "qualifications": [],
                                "cross_references": [],
                            }
                        )
            return a.CandidateBatch(findings=entries), call
        if role == "context_indexing":
            return a.ContextAudit(relevant_passages=[], unresolved_context=False), call
        claim = json.loads(prompt[prompt.index("{") :])["candidate"]
        status = "SUPPORTED"
        if negative and claim["category"] in {"PAYMENT", "PRIVACY"}:
            status = "UNSUPPORTED"
        if negative and claim["category"] == "DISPUTE":
            status = "AMBIGUOUS"
        response = verdict(status)
        if negative and "irrevocable" in claim["quote"]:
            response.category_consistent = False
        return response, call

    monkeypatch.setattr(a, "generate_with_fallback", generate)
    result = a.analyze(
        chunk_sections(sections), sections, [{"name": "groq", "key": "synthetic", "model": "synthetic"}]
    )
    assert len(result["findings"]) == 7
    assert sum(f["support_status"] == "SUPPORTED" for f in result["findings"]) == expected_supported
    assert all(
        c["match_status"] == "EXACT" and c["page"] in {1, 2}
        for f in result["findings"]
        for c in f["citations"]
    )
    if negative:
        assert sum(f["support_status"] == "UNSUPPORTED" for f in result["findings"]) == 2
        assert any(
            f["verification"].get("error_code") == "PROVIDER_CATEGORY_MISMATCH" for f in result["findings"]
        )
    summary = summarize(
        result["findings"],
        sections,
        result["coverage"],
        "PARTIAL_COMPLETION" if result["partial"] else "COMPLETED",
    )
    assert summary["counts"]["verified"] == expected_supported
    if negative:
        assert summary["level"] == "Not Determinable"
