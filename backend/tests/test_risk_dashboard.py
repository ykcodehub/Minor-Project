"""Synthetic evidence, pagination and request-budget regressions; no real inference."""

import json
import os
import time
from pathlib import Path

import httpx
import pymupdf
import pytest
from conftest import login_guest

from app import worker
from app.config import settings
from app.providers.base import ProviderError, configured_provider
from app.services.analysis import Verdict, _verification_prompt
from app.services.ingest import extract
from app.services.summary import assess_finding, summarize

CLAUSES = [
    ("RISK_NOTE", "The customer accepts unlimited liability for all service losses."),
    ("RESTRICTION", "The customer grants an irrevocable license to submitted materials."),
    ("PAYMENT", "Invoices must be paid within thirty days."),
    ("PRIVACY", "Personal data may be shared with service providers only with consent."),
    ("TERMINATION", "The supplier may terminate service on seven days notice."),
    ("DISPUTE", "Disputes must be resolved by arbitration in the stated venue."),
    ("RIGHT", "The customer may request a copy of their stored records."),
]


def agreement_pdf():
    doc = pymupdf.open()
    for number in range(2):
        page = doc.new_page()
        for block in range(18):
            index = (
                block
                if number == 0 and block < 4
                else block - 5
                if number == 1 and 9 <= block <= 11
                else None
            )
            text = (
                CLAUSES[index][1]
                if index is not None
                else (
                    f"Administrative record {number + 1}.{block + 1}. "
                    + "Service records describe routine administrative procedures and document retention. "
                    * 10
                )
            )
            assert (
                page.insert_textbox(
                    pymupdf.Rect(30, 25 + block * 43, 565, 65 + block * 43), text, fontsize=5.5
                )
                >= 0
            )
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_has_two_pages_and_thirty_six_blocks_without_offset_changes():
    result = extract(agreement_pdf(), "synthetic.pdf")
    assert result["coverage"]["pages_total"] == result["coverage"]["pages_extracted"] == 2
    assert len(result["sections"]) == 36
    assert {s["page"] for s in result["sections"]} == {1, 2}
    assert len({s["id"] for s in result["sections"]}) == 36


@pytest.mark.parametrize(
    "provider,model",
    [("gemini", "gemini-3.6-flash"), ("groq", "openai/gpt-oss-20b"), ("openrouter", "test/structured:free")],
)
def test_two_page_agreement_to_verified_risk_summary(client, monkeypatch, provider, model):
    login_guest(client)
    cfg = settings()
    for name in ("gemini", "groq", "openrouter"):
        monkeypatch.setattr(cfg, name + "_api_key", "synthetic" if name == provider else "")
    monkeypatch.setattr(cfg, provider + "_model", model)
    original = httpx.Client
    requests = []

    def respond(request):
        started = time.perf_counter()
        payload = json.loads(request.content)
        prompt = (
            payload["contents"][0]["parts"][0]["text"]
            if provider == "gemini"
            else payload["messages"][1]["content"]
        )
        role = (
            "candidate_generation"
            if prompt.startswith("Extract")
            else "context_indexing"
            if prompt.startswith("Index every")
            else "semantic_verification"
        )
        if role == "candidate_generation":
            findings = []
            for p in json.loads(prompt[prompt.index("[") :]):
                for category, quote in CLAUSES:
                    if quote not in p["text"]:
                        continue
                    start = p["start_offset"] + p["text"].index(quote)
                    findings.append(
                        {
                            "source_id": p["source_id"],
                            "section_id": p["section_id"],
                            "page": p["page"],
                            "quote": quote,
                            "start": start,
                            "end": start + len(quote),
                            "category": category,
                            "statement": quote,
                            "rationale": "Explicit term.",
                            "qualifications": [],
                            "cross_references": [],
                        }
                    )
            assert len(findings) <= 6
            output = {"findings": findings}
        elif role == "context_indexing":
            passages = json.loads(prompt[prompt.index("[") :])
            relevant = []
            for p in passages:
                quote = CLAUSES[3][1]
                if quote in p["text"]:
                    start = p["start_offset"] + p["text"].index(quote)
                    relevant.append(
                        {
                            "source_id": p["source_id"],
                            "section_id": p["section_id"],
                            "page": p["page"],
                            "quote": quote,
                            "start": start,
                            "end": start + len(quote),
                        }
                    )
            output = {"relevant_passages": relevant, "unresolved_context": False}
        else:
            data = json.loads(prompt[prompt.index("{") :])
            assert any(data["candidate"]["quote"] in p["text"] for p in data["context"])
            if provider == "openrouter":
                assert payload["reasoning"] == {"enabled": False}
            output = {
                "support_status": "SUPPORTED",
                "rationale": "The exact quoted condition supports this claim.",
                "missing_qualifiers": [],
                "unresolved_references": [],
            }
        adapter = configured_provider({"name": provider, "model": model, "key": "synthetic"})
        usage = adapter.request_usage(payload)
        assert usage["estimated_request_tokens"] <= usage["request_token_limit"]
        text = json.dumps(output)
        requests.append(
            dict(
                role=role,
                **usage,
                estimated_output_tokens=adapter.count_tokens(text),
                mock_handler_seconds=time.perf_counter() - started,
            )
        )
        if provider == "gemini":
            return httpx.Response(
                200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}
            )
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": text}}]}
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    start = time.perf_counter()
    uploaded = client.post(
        "/api/v1/sources/upload", files={"file": ("synthetic-risk.pdf", agreement_pdf(), "application/pdf")}
    )
    assert uploaded.status_code == 202, uploaded.text
    assert worker.run_once()
    sid = uploaded.json()["source_id"]
    source = client.get(f"/api/v1/sources/{sid}").json()
    assert source["coverage"]["pages_total"] == 2 and len(source["sections"]) == 36
    created = client.post(
        "/api/v1/analyses",
        json={
            "source_ids": [sid],
            "provider": provider,
            "fallback_providers": [],
            "consent": True,
            "privacy_mode": "external",
        },
    )
    assert created.status_code == 202, created.text
    assert worker.run_once()
    aid = created.json()["analysis_id"]
    job = client.get(f"/api/v1/jobs/{created.json()['job_id']}").json()
    summary = client.get(f"/api/v1/analyses/{aid}/summary").json()["summary"]
    assert job["state"] == "COMPLETED", job
    assert summary["counts"]["verified"] == 7
    assert summary["risk_counts"] == {"High": 2, "Moderate": 4, "Low": 1, "Unassessed": 0}
    assert summary["level"] == "High" and summary["priority_index"] == 3
    high = client.get(f"/api/v1/analyses/{aid}/findings?severity=High&group_by=severity").json()
    assert len(high) == 2 and all(f["risk_assessment"]["level"] == "High" for f in high)
    assert all(
        f["citations"][0]["page"] in (1, 2) for values in summary["risk_groups"].values() for f in values
    )
    report = os.getenv("VERIORA_RISK_BENCHMARK_REPORT")
    if report:
        target = Path(report)
        rows = json.loads(target.read_text()) if target.exists() else []
        rows.append(
            {
                "provider": provider,
                "model": model,
                "mock_inference": True,
                "pages": 2,
                "blocks": 36,
                "state": job["state"],
                "verified": 7,
                "risk_counts": summary["risk_counts"],
                "wall_seconds": round(time.perf_counter() - start, 3),
                "requests": requests,
                "retries": 0,
            }
        )
        target.write_text(json.dumps(rows, indent=2) + "\n")


def test_verification_wire_deduplicates_and_strips_parser_metadata():
    candidate = {
        "source_id": "s",
        "section_id": "r",
        "quote": "Payment is due.",
        "statement": "Payment is due.",
        "rationale": "not needed",
        "cross_references": [],
    }
    context = [
        {
            "id": "r",
            "source_id": "s",
            "page": 2,
            "text": "Payment is due.",
            "locator": {"private_parser_data": "x" * 10000},
        },
        {"section_id": "r", "source_id": "s", "text": "Payment is due."},
    ]
    data = json.loads(_verification_prompt(candidate, context, True).split("\n")[-1])
    assert (
        len(data["context"]) == 1
        and "locator" not in data["context"][0]
        and "rationale" not in data["candidate"]
    )


def test_incomplete_high_attention_does_not_become_safe_or_scored():
    text = CLAUSES[0][1]
    finding = {
        "id": "f",
        "finding_id": "f",
        "category": "RISK_NOTE",
        "support_status": "AMBIGUOUS",
        "statement": text,
        "citations": [
            {
                "source_id": "s",
                "section_id": "r",
                "quote": text,
                "start": 0,
                "end": len(text),
                "page": 1,
                "match_status": "EXACT",
            }
        ],
    }
    summary = summarize(
        [finding], [{"id": "r", "source_id": "s", "text": text, "page": 1}], {}, "PARTIAL_COMPLETION"
    )
    assert summary["level"] == "Not Determinable" and summary["priority_index"] is None
    assert summary["risk_counts"]["High"] == 0 and assess_finding(finding)["level"] == "Needs Review"


def test_semantic_length_does_not_retry_a_larger_reservation_that_cannot_fit(monkeypatch):
    original = httpx.Client
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "length", "message": {"content": ""}}],
                "usage": {"completion_tokens": 2048, "completion_tokens_details": {"reasoning_tokens": 2048}},
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    p = configured_provider({"name": "openrouter", "model": "test/structured:free", "key": "synthetic"})
    _, _, payload = p.request("s", "p", Verdict.model_json_schema())
    payload["max_tokens"] = 2048
    payload["reasoning"] = {"enabled": False}
    p.request_tokens = p.request_usage(payload)["estimated_input_tokens"] + 2048 + 100
    with pytest.raises(ProviderError, match="PROVIDER_REASONING_EXHAUSTED") as exc:
        p.generate("s", "p", Verdict, "semantic_verification")
    assert len(seen) == 1 and exc.value.model_calls[0]["reasoning_tokens"] == 2048


def test_existing_synthetic_agreement_preserves_two_pages():
    path = Path(__file__).parent / "fixtures" / "synthetic_contract.pdf"
    result = extract(path.read_bytes(), path.name)
    assert result["coverage"]["pages_total"] == 2
    assert {s["page"] for s in result["sections"]} == {1, 2}


def test_large_section_review_uses_exact_neighborhood_after_complete_audit(monkeypatch):
    from app.services import analysis as a
    from app.services.context_index import SourceWideIndex

    quote = "Invoices must be paid within thirty days."
    prefix = "Routine administrative wording. " * 800
    section = {"id": "r", "source_id": "s", "page": 2, "text": prefix + quote + prefix}
    candidate = {
        "section_id": "r",
        "source_id": "s",
        "page": 2,
        "quote": quote,
        "start": len(prefix),
        "end": len(prefix) + len(quote),
        "statement": quote,
        "cross_references": [],
    }
    seen = []

    def generate(configs, system, prompt, schema, role):
        if role == "context_indexing":
            return a.ContextAudit(relevant_passages=[], unresolved_context=False), [
                {"provider": "openrouter"}
            ]
        data = json.loads(prompt[prompt.index("{") :])
        seen.extend(data["context"])
        assert len(prompt) < 5000
        return a.Verdict(
            support_status="SUPPORTED",
            rationale="Explicit term.",
            missing_qualifiers=[],
            unresolved_references=[],
        ), [{"provider": "openrouter", "model": "test/structured:free"}]

    monkeypatch.setattr(a, "generate_with_fallback", generate)
    result, _ = SourceWideIndex([section]).review(
        candidate, [{"name": "openrouter", "model": "test/structured:free", "key": "synthetic"}]
    )
    assert result["support_status"] == "SUPPORTED" and result["source_index"]["complete"]
    passage = seen[0]
    assert passage["text"] == section["text"][passage["start_offset"] : passage["end_offset"]]
    assert quote in passage["text"]


def test_confirmed_repeated_reasoning_exhaustion_skips_only_verification_role(monkeypatch):
    from app.providers.base import generate_with_fallback

    original = httpx.Client
    seen = []

    def handler(request):
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

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: None)
    config = {
        "name": "openrouter",
        "model": "test/structured:free",
        "key": "synthetic",
        "budget": {"calls": 0, "tokens": 0, "max_calls": 100, "max_tokens": 500000},
    }
    for _ in range(2):
        with pytest.raises(ProviderError, match="PROVIDER_REASONING_EXHAUSTED"):
            generate_with_fallback([config], "s", "p", Verdict, "semantic_verification")
    assert len(seen) == 1
    assert ("openrouter", "semantic_verification") in config["budget"]["exhausted_reasoning_tasks"]
    assert ("openrouter", "candidate_generation") not in config["budget"]["exhausted_reasoning_tasks"]
