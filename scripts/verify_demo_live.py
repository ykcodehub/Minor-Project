"""Approved synthetic-only, zero-price live evaluation; no production DB access."""

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings, settings
from app.providers.base import ProviderError
from app.providers.model_policy import eligible_endpoint, model_info
from app.services.analysis import analyze, ask
from app.services.chunking import chunk_sections
from app.services.context_index import SourceWideIndex
from app.services.ingest import extract
from app.services.localization import _localize_batch
from app.services.summary import summarize
from app.services.verification import verify_quote

MODEL = "dots-studio/dots-3-note-preview:free"


class LiveGateError(RuntimeError):
    """Abort the whole controlled run; normal partial-result recovery must not catch it."""


def check_live_response(response, call):
    if response.status_code != 200:
        from app.providers.diagnostics import error_details

        call.update(error_details(response))
        raise LiveGateError("LIVE_PROVIDER_HTTP_" + str(response.status_code))
    try:
        raw = response.json()
        call.update(
            response_model=raw.get("model"),
            actual_provider=raw.get("provider"),
            usage=raw.get("usage"),
            finish_reason=(raw.get("choices") or [{}])[0].get("finish_reason"),
        )
        if Decimal(str((raw.get("usage") or {}).get("cost", "NaN"))) != 0:
            raise LiveGateError("ZERO_COST_RESPONSE_UNCONFIRMED")
    except (ValueError, TypeError, AttributeError, InvalidOperation):
        raise LiveGateError("LIVE_RESPONSE_SHAPE_UNCONFIRMED") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-dots-synthetic", action="store_true")
    parser.add_argument("--compact-fixture", action="store_true")
    parser.add_argument("--prior-report", type=Path)
    parser.add_argument("--report", type=Path, default=ROOT / "docs/benchmarks/college_live.json")
    args = parser.parse_args()
    report = {
        "model": MODEL,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "synthetic_only": True,
        "production_database_access": False,
        "limits": {"requests": 20, "reserved_tokens": 80000, "automatic_retries": 0},
        "stages": {},
        "calls": [],
        "inference_requests": 0,
    }
    budget = {
        "calls": 0,
        "tokens": 0,
        "max_calls": 20,
        "max_tokens": 80000,
        "deadline": time.monotonic() + 300,
    }
    prior_calls = prior_tokens = 0
    if args.prior_report:
        prior = json.loads(args.prior_report.read_text(encoding="utf-8"))
        if prior.get("model") != MODEL:
            raise ValueError("Prior report model mismatch")
        prior_calls = prior.get("cumulative_requests", prior["inference_requests"])
        prior_tokens = prior.get("cumulative_reserved_tokens", prior["reserved_tokens"])
        assert type(prior_calls) is int and type(prior_tokens) is int
        assert 0 <= prior_calls <= 20 and 0 <= prior_tokens <= 80000
        budget["max_calls"] -= prior_calls
        budget["max_tokens"] -= prior_tokens
    report["prior_consumed"] = {"requests": prior_calls, "reserved_tokens": prior_tokens}
    report["fixture"] = (
        "compact_authored_two_page" if args.compact_fixture else "benchmark_two_page_36_blocks"
    )
    started = time.monotonic()
    active_stage = "preflight"
    original_post = httpx.Client.post
    try:
        if not args.approve_dots_synthetic:
            raise ProviderError("SYNTHETIC_MODEL_CONSENT_REQUIRED")
        private = Settings()
        key = private.openrouter_api_key
        if not key:
            raise ProviderError("PROVIDER_NOT_CONFIGURED")
        info = model_info(MODEL)
        endpoint = eligible_endpoint(MODEL)
        if any(Decimal(str(info.get("pricing", {}).get(k, "-1"))) != 0 for k in ("prompt", "completion")):
            raise ProviderError("ZERO_PRICE_NOT_CONFIRMED")
        if endpoint.get("status") != 0 or (endpoint.get("uptime_last_5m") or 0) <= 0:
            raise ProviderError("ENDPOINT_AVAILABILITY_UNCONFIRMED")
        report["preflight"] = {
            "catalog_pricing": info["pricing"],
            "endpoint_pricing": endpoint["pricing"],
            "provider": endpoint.get("provider_name"),
            "status": endpoint["status"],
            "uptime_last_5m": endpoint.get("uptime_last_5m"),
            "supported_parameters": endpoint["supported_parameters"],
            "data_policy_scope": "Only generated synthetic agreement, synthetic questions and annotations; no personal/confidential content.",
        }
        report["stages"][active_stage] = "PASS"

        # Capture credential before isolating all app imports; never place it in report/prompt.
        runtime = ROOT / "backend/private-data" / ("controlled-live-" + uuid.uuid4().hex)
        runtime.mkdir(parents=True)
        os.environ.update(
            ENVIRONMENT="test",
            DATABASE_URL="sqlite:///" + (runtime / "isolated.db").as_posix(),
            STORAGE_BACKEND="filesystem",
            SECURE_COOKIES="false",
            SESSION_COOKIE_SAMESITE="lax",
            GOOGLE_CLIENT_ID="",
            GOOGLE_CLIENT_SECRET="",
            SMTP_HOST="",
            GEMINI_API_KEY="",
            GROQ_API_KEY="",
            OPENROUTER_API_KEY="",
        )
        settings.cache_clear()
        from app.db import Base, SessionLocal, engine
        from app.models import Analysis, AnalysisSource, Finding, Job, ModelCall, Section, Source, User, now
        from app.services.checkpoints import RequestCheckpoints

        assert engine.dialect.name == "sqlite"
        Base.metadata.create_all(engine)
        sys.path.insert(0, str(ROOT / "backend/tests"))
        from test_risk_dashboard import CLAUSES, agreement_pdf

        pdf = (
            (ROOT / "frontend/public/demo/synthetic-agreement.pdf").read_bytes()
            if args.compact_fixture
            else agreement_pdf()
        )
        extracted = extract(pdf, "synthetic-two-page.pdf")
        sections = extracted["sections"]
        assert extracted["coverage"]["pages_total"] == 2
        with SessionLocal() as db:
            user = User(is_guest=True, preferred_provider="openrouter", authorized_providers=["openrouter"])
            db.add(user)
            db.flush()
            job = Job(owner_id=user.id, kind="analysis", state="PROCESSING", lease_token="controlled-live")
            db.add(job)
            source = Source(
                owner_id=user.id,
                original_name="Synthetic two-page agreement.pdf",
                kind="file",
                object_key="synthetic-local-only",
                sha256=hashlib.sha256(pdf).hexdigest(),
                status="READY",
                expires_at=now() + timedelta(hours=1),
            )
            db.add(source)
            db.flush()
            record = Analysis(owner_id=user.id, job_id=job.id)
            db.add(record)
            db.flush()
            aid, jid = record.id, job.id
            db.add(AnalysisSource(analysis_id=aid, source_id=source.id))
            for section in sections:
                section["source_id"] = source.id
                db.add(
                    Section(id=section["id"], source_id=source.id, ordinal=section["ordinal"], data=section)
                )
            db.commit()
        report["stages"]["isolated_database"] = "PASS"
        report["stages"]["extraction"] = "PASS"
        report["source"] = {"pages": 2, "blocks": len(sections), "sha256": hashlib.sha256(pdf).hexdigest()}
        current_role = ""

        def attempt(event):
            nonlocal current_role
            current_role = event["role"]

        config = {
            "name": "openrouter",
            "model": MODEL,
            "key": key,
            "retries": 0,
            "timeout": 30,
            "max_output_tokens": 2048 if args.compact_fixture else 4096,
            "candidate_text_tokens": 128 if args.compact_fixture else 1800,
            "no_output_recovery": True,
            "budget": budget,
            "operation": "controlled_synthetic_live",
            "on_attempt": attempt,
            "authorize": lambda: args.approve_dots_synthetic,
            "checkpoint": RequestCheckpoints(SessionLocal, jid, "controlled-live"),
            "job_id": jid,
            "analysis_id": aid,
        }

        def guarded_post(client, url, **kwargs):
            payload = kwargs.get("json") or {}
            if str(url) != "https://openrouter.ai/api/v1/chat/completions" or payload.get("model") != MODEL:
                raise ProviderError("UNAUTHORIZED_OUTBOUND_REQUEST")
            if report["inference_requests"] >= budget["max_calls"] or budget["tokens"] > budget["max_tokens"]:
                raise ProviderError("PROVIDER_OPERATION_BUDGET_EXCEEDED")
            # Recheck before EVERY inference; never allow stale health/price or a paid route.
            import app.providers.model_policy as policy

            policy._endpoint_cache.clear()
            try:
                fresh = eligible_endpoint(MODEL)
            except ProviderError as exc:
                raise LiveGateError(exc.code) from None
            if fresh["tag"] not in payload.get("provider", {}).get("only", []):
                raise LiveGateError("ENDPOINT_CHANGED_PREFLIGHT_BLOCKED")
            if payload.get("provider", {}).get("max_price") != {"prompt": 0, "completion": 0, "request": 0}:
                raise LiveGateError("ZERO_PRICE_CEILING_REQUIRED")
            timer = time.monotonic()
            report["inference_requests"] += 1
            call = {"role": current_role, "requested_model": MODEL, "stage": active_stage}
            report["calls"].append(call)
            try:
                response = original_post(client, url, **kwargs)
                call.update(
                    http_status=response.status_code, latency_ms=round((time.monotonic() - timer) * 1000)
                )
                check_live_response(response, call)
                return response
            except httpx.HTTPError as exc:
                call.update(
                    error_type=type(exc).__name__, latency_ms=round((time.monotonic() - timer) * 1000)
                )
                raise LiveGateError("LIVE_TRANSPORT_" + type(exc).__name__) from None

        httpx.Client.post = guarded_post
        chunks = chunk_sections(sections)
        active_stage = "context_indexing"
        index, calls = SourceWideIndex(sections).prepare(sections[0]["source_id"], config)
        report["index_model_calls"] = calls
        report["stages"][active_stage] = "PASS" if index["complete"] else "FAIL"
        report["source_index"] = index
        active_stage = "analysis"
        result = analyze(chunks, sections, [config])
        report["analysis_model_calls"] = result["model_calls"]
        report["coverage"] = result["coverage"]
        report["warnings"] = result["warnings"]
        findings = result["findings"]
        for finding in findings:
            finding["finding_id"] = finding["id"]
            assert all(
                verify_quote(c, sections)["match_status"] in {"EXACT", "NORMALIZED"}
                for c in finding["citations"]
            )
        supported = [f for f in findings if f["support_status"] == "SUPPORTED"]
        report["findings"] = findings
        report["verified_findings"] = len(supported)
        report["known_fixture_clauses_recovered"] = sum(
            any(quote in c["quote"] for f in supported for c in f["citations"]) for _, quote in CLAUSES
        )
        report["stages"]["candidate_generation"] = "PASS" if findings else "FAIL"
        report["stages"]["evidence_quotes_pages"] = "PASS" if findings else "FAIL"
        report["stages"]["semantic_verification"] = (
            "PASS" if supported and len(supported) == len(findings) and not result["partial"] else "FAIL"
        )
        report["stages"][active_stage] = "PASS" if not result["partial"] and supported else "FAIL"
        active_stage = "summary"
        state = "PARTIAL_COMPLETION" if result["partial"] else "COMPLETED"
        summary = summarize(findings, sections, result["coverage"], state)
        report["summary"] = summary
        report["stages"][active_stage] = "PASS" if supported else "FAIL"
        with SessionLocal() as db:
            db.get(Analysis, aid).coverage = result["coverage"]
            db.get(Job, jid).state = state
            for finding in findings:
                db.add(Finding(id=finding["id"], analysis_id=aid, data=finding))
            for call in result["model_calls"]:
                db.add(ModelCall(job_id=jid, data=call))
            db.commit()
        report["stages"]["result_persistence"] = "PASS"
        config.pop("checkpoint")  # Analysis job is terminal; QA is a separate bounded task.
        active_stage = "question_answering"
        answer = ask("When must invoices be paid?", findings, sections, [config], retrieved_chunks=chunks)
        report["question_answer"] = answer
        report["stages"][active_stage] = (
            "PASS" if not answer.get("abstain") and answer.get("citations") else "FAIL"
        )
        for language in ("hi", "hinglish"):
            active_stage = "translation_" + language
            if not supported:
                report["stages"][active_stage] = "BLOCKED"
                continue
            translation, _ = _localize_batch(supported[:1], language, [config])
            report[active_stage] = {
                "translated_findings": 1,
                "total_supported_findings": len(supported),
                "values": translation,
            }
            report["stages"][active_stage] = "PASS"
    except LiveGateError as exc:
        report["stages"][active_stage] = "BLOCKED"
        report["error"] = str(exc)  # Constructed static codes only.
    except ProviderError as exc:
        report["stages"][active_stage] = "BLOCKED" if not report["inference_requests"] else "FAIL"
        report["error"] = exc.code
        report["failure_model_calls"] = exc.model_calls
    except (ValueError, KeyError, TypeError, AssertionError, OSError) as exc:
        report["stages"][active_stage] = "FAIL"
        report["error"] = type(exc).__name__  # Never stringify exceptions containing configuration.
    finally:
        httpx.Client.post = original_post
        for stage in (
            "preflight",
            "isolated_database",
            "extraction",
            "candidate_generation",
            "context_indexing",
            "semantic_verification",
            "evidence_quotes_pages",
            "summary",
            "question_answering",
            "translation_hi",
            "translation_hinglish",
        ):
            report["stages"].setdefault(stage, "BLOCKED")
        report["reserved_tokens"] = budget["tokens"]
        report["cumulative_requests"] = prior_calls + report["inference_requests"]
        report["cumulative_reserved_tokens"] = prior_tokens + budget["tokens"]
        report["wall_seconds"] = round(time.monotonic() - started, 3)
        report["role_counts"] = dict(Counter(c["role"] for c in report["calls"]))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "stages",
                        "inference_requests",
                        "reserved_tokens",
                        "wall_seconds",
                        "role_counts",
                    )
                },
                indent=2,
            )
        )
        if report.get("error"):
            print("SANITIZED_ERROR", report["error"])


if __name__ == "__main__":
    main()
