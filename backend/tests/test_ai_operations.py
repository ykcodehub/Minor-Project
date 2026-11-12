"""Quota, coverage, translation and source-grounded QA using synthetic HTTP/DB only."""

import json
import os
import time
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from conftest import login_guest
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import Analysis, AnalysisCheckpoint, Finding, Job, RateBucket, User, now
from app.providers.base import ProviderError, configured_provider, generate_with_fallback
from app.services.analysis import CandidateBatch, ContextAudit
from app.services.context_index import SourceWideIndex
from app.services.provider_policy import providers_for


def metrics(name, started, **values):
    report = os.getenv("VERIORA_OPERATION_BENCHMARK_REPORT")
    if report:
        path = Path(report)
        rows = json.loads(path.read_text()) if path.exists() else []
        rows.append(
            {
                "operation": name,
                "mock_inference": True,
                "local_seconds": round(time.perf_counter() - started, 4),
                **values,
            }
        )
        path.write_text(json.dumps(rows, indent=2) + "\n")


def configure(monkeypatch):
    for name in ("gemini", "groq"):
        monkeypatch.setattr(settings(), name + "_api_key", "synthetic-" + name)
        monkeypatch.setattr(settings(), name + "_model", "synthetic-model")


def test_429_shared_across_roles_and_fresh_operations_only_authorized_fallback(client, monkeypatch):
    started = time.perf_counter()
    configure(monkeypatch)
    user_id = login_guest(client)["id"]
    original = httpx.Client
    seen = []

    def handle(request):
        seen.append(request.url.host)
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(429, headers={"Retry-After": "90"}, json={"error": {"message": "PRIVATE"}})
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"findings":[]}'}}]}
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: pytest.fail("429 must not sleep/retry"))
    with SessionLocal() as db:
        user = db.get(User, user_id)
        for role in ("candidate_generation", "semantic_verification"):
            configs = providers_for(
                user, {"provider": "gemini", "fallback_providers": ["groq"], "consent": True}
            )
            value, calls = generate_with_fallback(configs, "s", "p", CandidateBatch, role)
            assert not value.findings and calls[0]["outcome"] == "PROVIDER_RATE_LIMITED"
        # A fresh operation with no fallback never sends to an unauthorized service.
        with pytest.raises(ProviderError, match="PROVIDER_RATE_LIMITED"):
            generate_with_fallback(
                providers_for(user, {"provider": "gemini", "consent": True}),
                "s",
                "p",
                CandidateBatch,
                "candidate_generation",
            )
    assert seen == ["generativelanguage.googleapis.com", "api.groq.com", "api.groq.com"]
    with SessionLocal() as db:
        row = db.scalar(select(RateBucket).where(RateBucket.id.like("ai-cooldown:%")))
        assert row and "synthetic" not in row.id
    metrics(
        "quota_shared",
        started,
        http_requests=len(seen),
        primary_rate_limited_requests=1,
        fallback_http_requests=2,
        shared_retry_seconds=90,
    )


def test_cooldown_expires_and_credentials_are_isolated(client, monkeypatch):
    from app.services import provider_quota

    current = now()
    monkeypatch.setattr(provider_quota, "now", lambda: current)
    config = {"name": "gemini", "model": "synthetic", "key": "synthetic-one"}
    check, block = provider_quota.hooks(config, SessionLocal)
    block(120)
    assert check() == 120
    other, _ = provider_quota.hooks({**config, "key": "synthetic-two"}, SessionLocal)
    assert other() == 0
    current += timedelta(seconds=121)
    assert check() == 0


def test_cooldown_reuses_completed_checkpoint_without_new_reservation(client, monkeypatch):
    from app.services.checkpoints import RequestCheckpoints
    from app.services.provider_quota import hooks

    owner = login_guest(client)["id"]
    with SessionLocal() as db:
        job = Job(owner_id=owner, kind="analysis", state="PROCESSING", lease_token="current")
        db.add(job)
        db.commit()
        ident = job.id
    config = {"name": "gemini", "model": "synthetic", "key": "synthetic"}
    check, block = hooks(config, SessionLocal)
    config.update(
        quota_check=check,
        quota_block=block,
        checkpoint=RequestCheckpoints(SessionLocal, ident, "current"),
        budget={"calls": 0, "tokens": 0, "max_calls": 100, "max_tokens": 500000},
    )
    original = httpx.Client
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"findings":[]}'}]}}]
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    p = configured_provider(config)
    p.generate("s", "p", CandidateBatch, "candidate_generation")
    block(60)
    _, calls = p.generate("s", "p", CandidateBatch, "candidate_generation")
    assert calls[0]["cached"]
    with pytest.raises(ProviderError, match="PROVIDER_RATE_LIMITED"):
        p.generate("s", "different", CandidateBatch, "candidate_generation")
    assert len(seen) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AnalysisCheckpoint)) == 1


def test_zero_reviewed_windows_means_failed_audit_not_empty_source(monkeypatch):
    from app.services import analysis

    sections = [
        {"id": f"r{i}", "source_id": "s", "page": i + 1, "text": "Administrative service wording. " * 200}
        for i in range(3)
    ]
    monkeypatch.setattr(
        analysis,
        "generate_with_fallback",
        lambda *a: (_ for _ in ()).throw(ProviderError("PROVIDER_RATE_LIMITED")),
    )
    index = SourceWideIndex(sections)
    record, _ = index.prepare("s", {"name": "groq", "model": "synthetic", "key": "synthetic"})
    assert record["windows_indexed"] >= 3 and record["windows_reviewed"] == record["windows_validated"] == 0
    assert record["windows_unreviewed"] == record["windows_total"] and record["windows_attempted"] == 1
    assert record["window_states"][0] == "FAILED" and not record["complete"]
    assert "not semantic verification" in record["verification_scope"]


def test_unresolved_audit_response_is_reviewed_but_not_validated(monkeypatch):
    from app.services import analysis

    monkeypatch.setattr(
        analysis,
        "generate_with_fallback",
        lambda *a: (ContextAudit(relevant_passages=[], unresolved_context=True), []),
    )
    index = SourceWideIndex([{"id": "r", "source_id": "s", "page": 1, "text": "Payment is due."}])
    record, _ = index.prepare("s", {"name": "groq", "model": "synthetic", "key": "synthetic"})
    assert record["windows_reviewed"] == 1 and record["windows_validated"] == 0 and not record["complete"]


@pytest.mark.parametrize("language", ["hi", "hinglish"])
def test_partial_verified_translation_is_persisted_and_resumed_without_rebilling(
    client, monkeypatch, language
):
    from app.models import AnalysisSource, Source

    started = time.perf_counter()
    from app.services import localization

    configure(monkeypatch)
    owner = login_guest(client)["id"]
    with SessionLocal() as db:
        job = Job(
            owner_id=owner,
            kind="analysis",
            state="COMPLETED",
            payload={"provider": "gemini", "consent": True},
        )
        db.add(job)
        db.flush()
        record = Analysis(owner_id=owner, job_id=job.id)
        db.add(record)
        db.flush()
        aid = record.id
        source = Source(
            owner_id=owner,
            kind="text",
            original_name="Synthetic.txt",
            object_key="never-read",
            sha256="a" * 64,
            status="READY",
            expires_at=now() + timedelta(days=1),
        )
        db.add(source)
        db.flush()
        db.add(AnalysisSource(analysis_id=aid, source_id=source.id))
        for i in range(7):
            db.add(
                Finding(
                    id=f"f{i}",
                    analysis_id=aid,
                    data={
                        "category": "CLAUSE",
                        "statement": f"Original term {i}",
                        "rationale": "Stated",
                        "qualifications": [],
                        "support_status": "AMBIGUOUS",
                        "citations": [],
                    },
                )
            )
        db.commit()
    seen = []
    fail = True

    def batch(findings, language, providers):
        nonlocal fail
        ids = [f["id"] for f in findings]
        seen.append(ids)
        if ids[0] == "f4" and fail:
            fail = False
            raise ProviderError("PROVIDER_RATE_LIMITED")
        return {
            f["id"]: {
                "statement": "Translated " + f["statement"],
                "rationale": "Stated",
                "qualifications": [],
            }
            for f in findings
        }, []

    monkeypatch.setattr(localization, "_localize_batch", batch)
    assert client.post(f"/api/v1/analyses/{aid}/translations?language={language}").status_code == 503
    summary = client.get(f"/api/v1/analyses/{aid}/summary?language={language}").json()
    assert not summary["translation_ready"] and summary["translation_completed"] == 4
    assert client.post(f"/api/v1/analyses/{aid}/translations?language={language}").json()["ready"]
    assert client.get(f"/api/v1/analyses/{aid}/summary?language={language}").json()["translation_ready"]
    assert client.post(f"/api/v1/analyses/{aid}/translations?language={language}").json()["ready"]
    assert seen == [["f0", "f1", "f2", "f3"], ["f4", "f5", "f6"], ["f4", "f5", "f6"]]
    metrics(
        "translation_cache_" + language,
        started,
        method="service-mocked verified batches",
        batch_sizes=[len(ids) for ids in seen],
        cached_after_first_failure=4,
        completed_translations=7,
        retranslated_completed_batches=0,
    )


def test_oversized_qa_uses_bounded_generation_and_audits_uncited_sources(monkeypatch):
    started = time.perf_counter()
    from app.services.analysis import ask

    sections = [
        {
            "id": f"r{i}",
            "source_id": "s",
            "page": i + 1,
            "text": ("Invoices must be paid within thirty days. " if i == 0 else "")
            + "Administrative service record. " * 230,
        }
        for i in range(8)
    ]
    sections.append(
        {
            "id": "exception",
            "source_id": "other",
            "page": 1,
            "text": "Payment is paused while an invoice dispute is investigated.",
        }
    )
    chunks = [{"spans": [{"section_id": s["id"], "start": 0, "end": len(s["text"])}]} for s in sections[:8]]
    original = httpx.Client
    seen = []
    config = {
        "name": "openrouter",
        "model": "test/structured:free",
        "key": "synthetic",
        "budget": {"calls": 0, "tokens": 0, "max_calls": 100, "max_tokens": 500000},
    }

    def handle(request):
        payload = json.loads(request.content)
        prompt = payload["messages"][1]["content"]
        usage = configured_provider(config).request_usage(payload)
        assert usage["estimated_request_tokens"] <= 12000
        seen.append((prompt[:25], usage))
        if prompt.startswith("Answer the question"):
            p = json.loads(prompt[prompt.index("{") :])["passages"][0]
            quote = "Invoices must be paid within thirty days."
            output = {
                "answer": "Payment is due within thirty days, paused during invoice disputes.",
                "citations": [
                    {
                        "source_id": p["source_id"],
                        "section_id": p["section_id"],
                        "page": p["page"],
                        "quote": quote,
                        "start": 0,
                        "end": len(quote),
                    }
                ],
                "abstain": False,
                "limitations": [],
            }
        elif prompt.startswith("Index every"):
            relevant = []
            for p in json.loads(prompt[prompt.index("[") :]):
                if p["source_id"] == "s0" and p["text"].startswith("Payment is paused"):
                    relevant.append(
                        {
                            "source_id": p["source_id"],
                            "section_id": p["section_id"],
                            "page": p["page"],
                            "quote": p["text"],
                            "start": p["start_offset"],
                            "end": p["end_offset"],
                        }
                    )
            output = {"relevant_passages": relevant, "unresolved_context": False}
        else:
            assert "Payment is paused" in prompt
            output = {
                "support_status": "SUPPORTED",
                "rationale": "Exact qualified terms reviewed.",
                "missing_qualifiers": [],
                "unresolved_references": [],
            }
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    result = ask("When must invoices be paid?", [], sections, [config], retrieved_chunks=chunks)
    assert result["citations"][0]["start"] == 0 and result["verification"]["support_status"] == "SUPPORTED"
    assert result["retrieval"]["generation_scope_limited"]
    assert {r["source_id"] for r in result["verification"]["source_audits"]} == {"s", "other"}
    assert len(seen) < 100
    metrics(
        "oversized_question",
        started,
        http_requests=len(seen),
        source_sections=len(sections),
        selected_sources=2,
        max_estimated_semantic_input_tokens=max(
            u["estimated_input_tokens"] for prefix, u in seen if prefix.startswith("Review")
        ),
        max_estimated_request_tokens=max(u["estimated_request_tokens"] for _, u in seen),
        source_audits_complete=all(r["complete"] for r in result["verification"]["source_audits"]),
        exact_citations=len(result["citations"]),
        authoritative_token_usage=None,
    )


def test_translation_and_question_errors_are_not_analysis_failures(client):
    from app.models import AnalysisSource, ModelCall, Source

    owner = login_guest(client)["id"]
    with SessionLocal() as db:
        job = Job(owner_id=owner, kind="analysis", state="COMPLETED")
        db.add(job)
        db.flush()
        record = Analysis(owner_id=owner, job_id=job.id)
        db.add(record)
        db.flush()
        source = Source(
            owner_id=owner,
            kind="text",
            original_name="Synthetic.txt",
            object_key="unused",
            sha256="a" * 64,
            expires_at=now() + timedelta(days=1),
        )
        db.add(source)
        db.flush()
        db.add(AnalysisSource(analysis_id=record.id, source_id=source.id))
        for operation, role in [
            ("translation", "explanation_translation"),
            ("question", "semantic_verification"),
        ]:
            db.add(
                ModelCall(
                    job_id=job.id,
                    data={"operation": operation, "role": role, "outcome": "PROVIDER_RATE_LIMITED"},
                )
            )
        db.commit()
        aid = record.id
    assert client.get(f"/api/v1/analyses/{aid}/summary").json()["summary"]["failure_codes"] == []


@pytest.mark.parametrize("search_error", ["PROVIDER_INVALID_OUTPUT", "PROVIDER_CONTENT_BLOCKED"])
def test_failed_multilingual_search_does_not_skip_grounded_question_path(client, monkeypatch, search_error):
    from test_api import upload_text

    from app.models import AnalysisSource
    from app.services import analysis, localization

    configure(monkeypatch)
    owner = login_guest(client)["id"]
    sid = upload_text(client, "Invoices must be paid within thirty days.")["source_id"]
    with SessionLocal() as db:
        job = Job(
            owner_id=owner,
            kind="analysis",
            state="COMPLETED",
            payload={"provider": "gemini", "consent": True},
        )
        db.add(job)
        db.flush()
        record = Analysis(owner_id=owner, job_id=job.id)
        db.add(record)
        db.flush()
        aid = record.id
        db.add(AnalysisSource(analysis_id=aid, source_id=sid))
        db.commit()
    monkeypatch.setattr(
        localization,
        "retrieval_question",
        lambda *a: (_ for _ in ()).throw(ProviderError(search_error)),
    )
    seen = []

    def answer(question, findings, sections, providers, retrieved_chunks=None, language="en"):
        seen.append((question, language, retrieved_chunks))
        return {
            "answer": "Available document se confirm nahi kar sakta.",
            "citations": [],
            "limitations": [],
            "model_calls": [],
        }

    monkeypatch.setattr(analysis, "ask", answer)
    response = client.post(
        f"/api/v1/analyses/{aid}/questions", json={"question": "Kya payment due hai?", "language": "hinglish"}
    )
    if search_error == "PROVIDER_CONTENT_BLOCKED":
        assert (
            response.status_code == 503 and response.json()["code"] == "PROVIDER_CONTENT_BLOCKED" and not seen
        )
        return
    assert (
        response.status_code == 200
        and response.json()["retrieval_warning"] == "SEARCH_TRANSLATION_UNAVAILABLE"
    )
    assert seen and seen[0][1] == "hinglish"
    monkeypatch.setattr(
        analysis,
        "ask",
        lambda *a, **kw: (_ for _ in ()).throw(
            ProviderError(
                "PROVIDER_RATE_LIMITED",
                calls=[
                    {
                        "role": "question_answering",
                        "operation": "question",
                        "outcome": "PROVIDER_RATE_LIMITED",
                        "retry_after_seconds": 90,
                    }
                ],
            )
        ),
    )
    failed = client.post(
        f"/api/v1/analyses/{aid}/questions", json={"question": "When is payment due?", "language": "en"}
    )
    assert (
        failed.status_code == 503
        and failed.headers["Retry-After"] == "90"
        and failed.json()["code"] == "PROVIDER_RATE_LIMITED"
    )


def test_structured_retry_info_and_safe_429_wait(monkeypatch):
    original = httpx.Client
    seen = []
    waits = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            429,
            json={
                "error": {
                    "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "121s"}],
                    "message": "PRIVATE DOCUMENT",
                }
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    p = configured_provider(
        {"name": "gemini", "model": "synthetic", "key": "synthetic", "quota_block": waits.append}
    )
    with pytest.raises(ProviderError) as exc:
        p.generate("s", "p", CandidateBatch, "candidate_generation")
    assert len(seen) == 1 and waits == [121]
    assert exc.value.model_calls[0]["retry_after_seconds"] == 121
    assert "PRIVATE" not in json.dumps(exc.value.model_calls)


def test_sizing_excludes_rate_limited_primary_with_larger_context():
    from app.providers.base import budget_available_configs

    budget = {"calls": 0, "tokens": 0, "max_calls": 100, "max_tokens": 500000}
    primary = {
        "name": "gemini",
        "model": "synthetic",
        "key": "synthetic",
        "budget": budget,
        "quota_check": lambda: 90,
    }
    fallback = {"name": "groq", "model": "synthetic", "key": "synthetic", "budget": budget}
    assert budget_available_configs([primary, fallback]) == [fallback]
    assert "gemini" in budget["unavailable"]
    with pytest.raises(ProviderError, match="PROVIDER_RATE_LIMITED"):
        budget_available_configs([primary])


@pytest.mark.parametrize("without_assessment", [False, True])
def test_existing_verified_translation_cache_is_reused_without_credentials(
    client, monkeypatch, without_assessment
):
    import hashlib

    from app.api.analyses import finding_dict
    from app.models import AnalysisSource, LocalizedAnalysis, Source
    from app.services import localization

    owner = login_guest(client)["id"]
    with SessionLocal() as db:
        job = Job(owner_id=owner, kind="analysis", state="COMPLETED")
        db.add(job)
        db.flush()
        analysis = Analysis(owner_id=owner, job_id=job.id)
        db.add(analysis)
        db.flush()
        source = Source(
            owner_id=owner,
            kind="text",
            original_name="Synthetic",
            object_key="unused",
            sha256="a" * 64,
            expires_at=now() + timedelta(days=1),
        )
        db.add(source)
        db.flush()
        db.add(AnalysisSource(analysis_id=analysis.id, source_id=source.id))
        finding = Finding(
            id="f-legacy",
            analysis_id=analysis.id,
            data={
                "category": "CLAUSE",
                "statement": "Original term",
                "rationale": "Stated",
                "support_status": "AMBIGUOUS",
                "qualifications": [],
                "citations": [],
            },
        )
        db.add(finding)
        db.flush()
        original = finding_dict(finding)
        if without_assessment:
            original.pop("risk_assessment")
        stamp = hashlib.sha256(
            json.dumps([original], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        db.add(
            LocalizedAnalysis(
                analysis_id=analysis.id,
                language="hi",
                fingerprint=stamp,
                data={
                    "f-legacy": {
                        "statement": "Saved verified translation",
                        "rationale": "Stated",
                        "qualifications": [],
                    }
                },
            )
        )
        db.commit()
        aid = analysis.id
    monkeypatch.setattr(
        localization, "localize", lambda *a: pytest.fail("Legacy complete cache must not be regenerated")
    )
    response = client.get(f"/api/v1/analyses/{aid}/summary?language=hi").json()
    assert (
        response["translation_ready"]
        and response["translations"]["f-legacy"]["statement"] == "Saved verified translation"
    )
    assert client.post(f"/api/v1/analyses/{aid}/translations?language=hi").json()["ready"]


def test_fractional_provider_retry_delay_never_rounds_down():
    from app.api.analyses import ai_unavailable

    error = ai_unavailable(
        ProviderError("PROVIDER_RATE_LIMITED", calls=[{"retry_after_seconds": 0.5}]), "Ask Veriora"
    )
    assert error.headers["Retry-After"] == "1"
