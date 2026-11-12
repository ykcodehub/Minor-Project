"""Explicitly approved real OpenRouter inference through isolated HTTP APIs/worker.

No production database, settings, SMTP delivery or private documents are used.
The only mocks are the isolated process's provider configuration and test mail
transport; model responses are real and every inference is guarded and counted.
"""

import argparse
import json
import os
import secrets
import sys
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
import pymupdf
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from verify_demo_live import LiveGateError, check_live_response

from app.config import Settings, settings
from app.providers.base import configured_provider
from app.providers.model_policy import eligible_endpoint, model_info

MODEL = "dots-studio/dots-3-note-preview:free"
CLAUSES = [
    "Customer must pay each invoice within thirty calendar days after receiving it.",
    "Customer accepts unlimited liability for all direct losses caused by Customer's use of Service.",
    "Customer grants Supplier an irrevocable license to reproduce and use materials Customer uploads to Service.",
    "Supplier may share Customer's personal data with hosting providers only after Customer gives written consent.",
    "Either party may terminate Service for any reason by giving the other party seven calendar days' written notice.",
    "Customer may request a copy of their stored records at any time, and Supplier must deliver that copy within thirty calendar days.",
]


def synthetic_pdf():
    doc = pymupdf.open()
    for number, clauses in enumerate((CLAUSES[:3], CLAUSES[3:])):
        page = doc.new_page()
        page.insert_text((30, 40), f"SYNTHETIC SERVICE AGREEMENT - Page {number + 1}", fontsize=11)
        for index, clause in enumerate(clauses):
            assert (
                page.insert_textbox(
                    pymupdf.Rect(30, 95 + index * 140, 560, 190 + index * 140), clause, fontsize=10
                )
                >= 0
            )
    pdf = doc.tobytes(no_new_id=True, deflate=True)
    doc.close()
    return pdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-free-live", action="store_true")
    parser.add_argument("--report", type=Path, default=ROOT / "docs/benchmarks/final_live_acceptance.json")
    args = parser.parse_args()
    report = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "synthetic_only": True,
        "production_data_modified": False,
        "limits": {"requests": 20, "reserved_tokens": 80000, "automatic_retries": 0},
        "stages": {},
        "calls": [],
    }
    active = "preflight"
    gate_reason = None
    reserved = 0
    started = time.monotonic()
    original_post = httpx.Client.post
    try:
        if not args.approve_free_live:
            raise LiveGateError("EXPLICIT_LIVE_APPROVAL_REQUIRED")
        private = Settings()
        key = private.openrouter_api_key
        if not key:
            raise LiveGateError("OPENROUTER_CREDENTIAL_NOT_CONFIGURED")
        info, endpoint = model_info(MODEL), eligible_endpoint(MODEL)
        if any(Decimal(str(info.get("pricing", {}).get(k, "-1"))) != 0 for k in ("prompt", "completion")):
            raise LiveGateError("ZERO_PRICING_UNCONFIRMED")
        if (endpoint.get("uptime_last_5m") or 0) <= 0:
            raise LiveGateError("ENDPOINT_HEALTH_UNCONFIRMED")
        report["preflight"] = {
            "provider": endpoint.get("provider_name"),
            "endpoint_status": endpoint["status"],
            "catalog_pricing": info["pricing"],
            "endpoint_pricing": endpoint["pricing"],
            "supported_parameters": endpoint["supported_parameters"],
            "reasoning": info.get("reasoning"),
            "privacy_scope": "Generated fictional clauses only; credentials/session/email never enter prompts.",
        }
        report["stages"][active] = "PASS"
        runtime = ROOT / "backend/private-data" / ("final-acceptance-" + uuid.uuid4().hex)
        runtime.mkdir(parents=True)
        os.environ.update(
            ENVIRONMENT="test",
            DATABASE_URL="sqlite:///" + (runtime / "test.db").as_posix(),
            STORAGE_BACKEND="filesystem",
            STORAGE_PATH=str(runtime / "objects"),
            STORAGE_KEY=Fernet.generate_key().decode(),
            SECURE_COOKIES="false",
            SESSION_COOKIE_SAMESITE="lax",
            PUBLIC_URL="http://localhost:5173",
            ALLOWED_ORIGINS="http://localhost:5173",
            GOOGLE_CLIENT_ID="",
            GOOGLE_CLIENT_SECRET="",
            SMTP_HOST="synthetic.invalid",
            MAIL_FROM="synthetic@example.com",
            TEST_MAIL_OUTBOX=str(runtime / "mail.jsonl"),
            GEMINI_API_KEY="",
            GROQ_API_KEY="",
            OPENROUTER_API_KEY="",
            MAX_AI_CALLS_PER_OPERATION="20",
            MAX_AI_TOKENS_PER_OPERATION="80000",
            ANALYSIS_TIMEOUT_SECONDS="240",
        )
        settings.cache_clear()
        from fastapi.testclient import TestClient

        from app.db import Base, engine
        from app.main import app
        from app.services.context_index import SourceWideIndex
        from app.services.verification import verify_quote
        from app.worker import run_once

        assert engine.dialect.name == "sqlite"
        Base.metadata.create_all(engine)
        cfg = {
            "name": "openrouter",
            "model": MODEL,
            "key": key,
            "timeout": 30,
            "retries": 0,
            "max_output_tokens": 2048,
            "no_output_recovery": True,
        }

        def guarded_post(client, url, **kwargs):
            nonlocal gate_reason, reserved
            if isinstance(client, TestClient):
                return original_post(client, url, **kwargs)
            if gate_reason:
                raise LiveGateError(gate_reason)
            try:
                payload = kwargs.get("json") or {}
                if (
                    str(url) != "https://openrouter.ai/api/v1/chat/completions"
                    or payload.get("model") != MODEL
                ):
                    raise LiveGateError("UNAUTHORIZED_OUTBOUND_REQUEST")
                if len(report["calls"]) >= 20 or time.monotonic() - started > 240:
                    raise LiveGateError("LIVE_OPERATION_LIMIT")
                import app.providers.model_policy as policy

                policy._endpoint_cache.clear()
                fresh = eligible_endpoint(MODEL)
                if fresh["tag"] not in payload.get("provider", {}).get("only", []):
                    raise LiveGateError("ENDPOINT_CHANGED")
                if payload.get("provider", {}).get("max_price") != {
                    "prompt": 0,
                    "completion": 0,
                    "request": 0,
                }:
                    raise LiveGateError("ZERO_PRICE_CEILING_REQUIRED")
                usage = configured_provider(cfg).request_usage(payload)
                if reserved + usage["estimated_request_tokens"] > 80000:
                    raise LiveGateError("LIVE_TOKEN_LIMIT")
                reserved += usage["estimated_request_tokens"]
                prompt = payload["messages"][-1]["content"]
                role = next(
                    (
                        role
                        for prefix, role in (
                            ("Extract", "candidate_generation"),
                            ("Index every", "context_indexing"),
                            ("Review this candidate", "semantic_verification"),
                            ("Answer the question", "question_answering"),
                            ("Translate only", "explanation_translation"),
                            ("Check translation fidelity", "translation_verification"),
                        )
                        if prompt.startswith(prefix)
                    ),
                    "other",
                )
                call = {"stage": active, "role": role, "requested_model": MODEL, **usage}
                report["calls"].append(call)
                timer = time.monotonic()
                response = original_post(client, url, **kwargs)
                call.update(
                    http_status=response.status_code, latency_ms=round((time.monotonic() - timer) * 1000)
                )
                check_live_response(response, call)
                return response
            except Exception as exc:  # noqa: BLE001 - fail-closed outbound gate and secret-redaction boundary
                # Only constructed codes or exception type names; never response prose/keys.
                gate_reason = str(exc) if isinstance(exc, LiveGateError) else type(exc).__name__
                raise LiveGateError(gate_reason) from None

        def require(response, code=200):
            if response.status_code != code:
                raise LiveGateError("LOCAL_API_HTTP_" + str(response.status_code))
            return response.json()

        with (
            patch.object(type(settings()), "providers", lambda self: [cfg]),
            patch.object(httpx.Client, "post", guarded_post),
            TestClient(app, base_url="http://localhost") as client,
        ):
            client.headers["Origin"] = "http://localhost:5173"
            active = "local_verified_registration"
            password = secrets.token_urlsafe(20)
            require(
                client.post(
                    "/api/v1/auth/register",
                    json={"email": "controlled-demo@example.com", "password": password},
                ),
                202,
            )
            mail = json.loads((runtime / "mail.jsonl").read_text().splitlines()[-1])
            require(client.post("/api/v1/auth/verify", json={"token": mail["token"], "password": password}))
            profile = require(
                client.post(
                    "/api/v1/auth/login", json={"email": "controlled-demo@example.com", "password": password}
                )
            )
            client.headers["X-CSRF-Token"] = profile["csrf_token"]
            require(
                client.patch(
                    "/api/v1/me",
                    json={
                        "preferred_provider": "openrouter",
                        "authorized_providers": ["openrouter"],
                        "retention_days": 1,
                    },
                )
            )
            report["stages"][active] = "PASS_TEST_MAIL_TRANSPORT"
            active = "pdf_upload_extraction"
            pdf = synthetic_pdf()
            source_job = require(
                client.post(
                    "/api/v1/sources/upload", files={"file": ("synthetic-final.pdf", pdf, "application/pdf")}
                ),
                202,
            )
            assert run_once()
            source = require(client.get("/api/v1/sources/" + source_job["source_id"]))
            assert source["status"] == "READY" and source["coverage"]["pages_total"] == 2
            assert client.get("/api/v1/sources/" + source["id"] + "/original").content == pdf
            report["source"] = source
            report["expected_clauses"] = CLAUSES
            report["stages"][active] = "PASS"
            active = "context_indexing"
            sections = [{**s, "source_id": source["id"]} for s in source["sections"]]
            index, _ = SourceWideIndex(sections).prepare(source["id"], cfg)
            if gate_reason:
                raise LiveGateError(gate_reason)
            report["context_index"] = index
            report["stages"][active] = "PASS" if index["complete"] else "FAIL"
            active = "worker_analysis"
            created = require(
                client.post(
                    "/api/v1/analyses", json={"source_ids": [source["id"]], "privacy_mode": "external"}
                ),
                202,
            )
            assert run_once()
            if gate_reason:
                raise LiveGateError(gate_reason)
            aid = created["analysis_id"]
            job = require(client.get("/api/v1/jobs/" + created["job_id"]))
            analysis = require(client.get("/api/v1/analyses/" + aid))
            findings = require(client.get(f"/api/v1/analyses/{aid}/findings"))
            summary = require(client.get(f"/api/v1/analyses/{aid}/summary"))
            report.update(analysis=analysis, findings=findings, summary=summary, job_state=job["state"])
            supported = [f for f in findings if f["support_status"] == "SUPPORTED"]
            report["supported_findings"] = len(supported)
            report["stages"][active] = "PASS" if job["state"] == "COMPLETED" and supported else "FAIL"
            report["stages"]["summary_risk_data"] = (
                "PASS" if supported and summary["summary"]["counts"]["verified"] == len(supported) else "FAIL"
            )
            assert all(
                verify_quote(c, sections)["match_status"] in {"EXACT", "NORMALIZED"}
                for f in supported
                for c in f["citations"]
            )
            report["stages"]["verified_evidence_alignment"] = "PASS" if supported else "FAIL"
            active = "grounded_question"
            qa = require(
                client.post(
                    f"/api/v1/analyses/{aid}/questions",
                    json={"question": "When must the customer pay an invoice?", "language": "en"},
                )
            )
            if gate_reason:
                raise LiveGateError(gate_reason)
            report["question_answer"] = qa
            report["stages"][active] = (
                "PASS"
                if qa.get("citations") and qa.get("verification", {}).get("support_status") == "SUPPORTED"
                else "FAIL"
            )
            active = "report_downloads"
            for fmt in ("json", "pdf"):
                response = client.get(f"/api/v1/analyses/{aid}/exports?format={fmt}")
                if response.status_code != 200 or not response.content:
                    raise LiveGateError("EXPORT_FAILED")
            report["stages"][active] = "PASS"
            for language in ("hi", "hinglish"):
                active = "translation_" + language
                response = client.post(f"/api/v1/analyses/{aid}/translations?language={language}")
                if gate_reason:
                    raise LiveGateError(gate_reason)
                translated = require(response)
                localized_summary = require(client.get(f"/api/v1/analyses/{aid}/summary?language={language}"))
                report[active] = localized_summary
                report["stages"][active] = (
                    "PASS"
                    if translated.get("ready") and localized_summary.get("translation_ready")
                    else "FAIL"
                )
            report["stages"]["history"] = "PASS" if require(client.get("/api/v1/sources")) else "FAIL"
    except Exception as exc:  # noqa: BLE001 - never print exception prose containing private configuration
        report["stages"][active] = "BLOCKED" if isinstance(exc, LiveGateError) else "FAIL"
        report["error"] = str(exc) if isinstance(exc, LiveGateError) else type(exc).__name__
    finally:
        for stage in (
            "preflight",
            "pdf_upload_extraction",
            "context_indexing",
            "worker_analysis",
            "summary_risk_data",
            "verified_evidence_alignment",
            "grounded_question",
            "report_downloads",
            "translation_hi",
            "translation_hinglish",
            "history",
        ):
            report["stages"].setdefault(stage, "BLOCKED")
        report.update(
            inference_requests=len(report["calls"]),
            reserved_estimated_tokens=reserved,
            wall_seconds=round(time.monotonic() - started, 3),
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    k: report.get(k)
                    for k in (
                        "stages",
                        "error",
                        "inference_requests",
                        "reserved_estimated_tokens",
                        "wall_seconds",
                        "supported_findings",
                    )
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
