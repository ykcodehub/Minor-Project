import hashlib
import json
from datetime import timedelta
from pathlib import Path

from conftest import login_guest
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import AuditEvent, EvidenceSpan, Finding, Job, Section, Source, now
from app.services import storage
from app.worker import cleanup, run_once


def upload_text(client, text="The user must pay invoices within thirty days."):
    response = client.post("/api/v1/sources/text", json={"name": "Agreement", "text": text})
    assert response.status_code == 202, response.text
    assert run_once()
    return response.json()


def register(client, email="reviewer@example.com"):
    from unittest.mock import patch

    data = {"email": email, "password": "safe-test-password-2026"}
    cfg = settings()
    with (
        patch.object(cfg, "smtp_host", "synthetic.invalid"),
        patch.object(cfg, "mail_from", "noreply@example.com"),
    ):
        response = client.post("/api/v1/auth/register", json=data)
        assert response.status_code == 202, response.text
        token = client.veriora_mail[-1]["token"]
        verified = client.post("/api/v1/auth/verify", json={"token": token, "password": data["password"]})
        assert verified.status_code == 200, verified.text
    response = client.post("/api/v1/auth/login", json=data)
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()


def test_auth_csrf_origin_logout(client):
    assert client.get("/api/v1/me").status_code == 401

    login_guest(client)
    assert client.get("/api/v1/me").json()["is_guest"]
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "bad"}).status_code == 403
    assert (
        client.post("/api/v1/auth/logout", headers={"Origin": "https://attacker.example"}).status_code == 403
    )
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_register_upgrades_guest_without_losing_owned_sources(client):
    guest = login_guest(client)
    source = upload_text(client)
    account = register(client)
    assert not account["is_guest"]
    assert account["id"] == guest["id"]
    assert client.get("/api/v1/sources/" + source["source_id"]).status_code == 200


def test_ingest_persistence_original_hash_and_delete(client):
    login_guest(client)
    text = "1. Privacy\nWe collect account data only with consent.\n\n2. Exception\nDisclosure may be required by law."
    result = upload_text(client, text)
    job = client.get("/api/v1/jobs/" + result["job_id"]).json()
    assert job["state"] == "COMPLETED", job
    source = client.get("/api/v1/sources/" + result["source_id"]).json()
    assert source["sections"]
    assert source["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert source["status"] == "READY"
    assert client.get("/api/v1/sources/" + source["id"] + "/original").content == text.encode()
    with SessionLocal() as db:
        record = db.get(Source, source["id"])
        assert text.encode() not in storage.path(record.object_key).read_bytes()
        object_key = record.object_key
    assert client.delete("/api/v1/sources/" + source["id"]).status_code == 204
    assert client.get("/api/v1/sources/" + source["id"]).status_code == 404
    assert not storage.path(object_key).exists()
    with SessionLocal() as db:
        assert not db.scalars(select(Section)).all()
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "source.deleted"))


def test_cross_user_isolation(client):
    login_guest(client)
    result = upload_text(client)
    client.cookies.clear()
    login_guest(client)
    for path in (
        "sources/" + result["source_id"],
        "jobs/" + result["job_id"],
        "sources/" + result["source_id"] + "/original",
    ):
        response = client.get("/api/v1/" + path)
        assert response.status_code == 404
        assert "invoices" not in response.text
    assert client.delete("/api/v1/sources/" + result["source_id"]).status_code == 404
    assert client.get("/api/v1/sources").json() == []


def test_unconfigured_provider_and_confidential_mode_block(client):
    login_guest(client)
    source = upload_text(client)
    body = {
        "source_ids": [source["source_id"]],
        "provider": "gemini",
        "consent": True,
        "privacy_mode": "external",
    }
    assert client.post("/api/v1/analyses", json=body).status_code == 503
    body["privacy_mode"] = "confidential"
    assert client.post("/api/v1/analyses", json=body).status_code == 422


def test_invalid_file_and_error_redaction(client):
    login_guest(client)
    response = client.post("/api/v1/sources/upload", files={"file": ("secret.pdf", b"not a PDF")})
    assert response.status_code == 202
    assert run_once()
    job = client.get("/api/v1/jobs/" + response.json()["job_id"]).json()
    assert job["state"] == "FAILED"
    assert "not a PDF" in job["error"]
    response = client.post("/api/v1/sources/upload", files={"file": ("payload.exe", b"MZ")})
    assert response.status_code == 422
    assert "Traceback" not in response.text


def test_source_ids_do_not_collide_for_duplicate_content(client):
    login_guest(client)
    first = upload_text(client)
    second = upload_text(client)
    one = client.get("/api/v1/sources/" + first["source_id"]).json()
    two = client.get("/api/v1/sources/" + second["source_id"]).json()
    assert one["sha256"] == two["sha256"]
    assert one["sections"][0]["id"] != two["sections"][0]["id"]


def test_cancellation_and_quota(client):
    login_guest(client)
    body = {"name": "contract", "text": "You must pay."}
    first = client.post("/api/v1/sources/text", json=body).json()
    assert client.post("/api/v1/sources/text", json=body).status_code == 429
    assert client.post("/api/v1/jobs/" + first["job_id"] + "/cancel").status_code == 200
    assert not run_once()
    assert client.post("/api/v1/jobs/" + first["job_id"] + "/retry").status_code == 200
    assert run_once()


def test_retention_cleanup(client):
    login_guest(client)
    result = upload_text(client)
    with SessionLocal() as db:
        source = db.get(Source, result["source_id"])
        source.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/sources/" + result["source_id"]).status_code == 404
    cleanup()
    assert client.get("/api/v1/sources").json() == []


def test_account_login_recovery_settings(client):
    user = register(client)
    response = client.patch("/api/v1/me", json={"retention_days": 7, "preferred_provider": "groq"})
    assert response.status_code == 200
    assert response.json()["retention_days"] == 7
    assert client.get("/api/v1/me/export").status_code == 200
    assert client.post("/api/v1/auth/recover", json={"email": user["email"]}).status_code == 503
    client.post("/api/v1/auth/logout")
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": "incorrect-password"}
        ).status_code
        == 401
    )
    response = client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": "safe-test-password-2026"}
    )
    assert response.status_code == 200


def test_integrated_analysis_reports_qa_delete(client, monkeypatch):
    import app.services.analysis as service

    register(client)
    source = upload_text(client, "The user must pay invoices within thirty days.")
    cfg = settings()
    monkeypatch.setattr(cfg, "gemini_api_key", "test-only-never-real-key")
    monkeypatch.setattr(cfg, "gemini_model", "test-only-model")

    def fake_analyze(chunks, sections, providers, on_progress):
        assert providers[0]["key"] == "test-only-never-real-key"
        section = sections[0]
        quote = section["text"]
        on_progress("VERIFYING", 1, 1)
        return {
            "findings": [
                {
                    "category": "OBLIGATION",
                    "statement": "The user must pay within thirty days.",
                    "rationale": "Payment deadline.",
                    "qualifications": [],
                    "support_status": "SUPPORTED",
                    "verification": {"method": "synthetic test only"},
                    "citations": [
                        {
                            "source_id": section["source_id"],
                            "section_id": section["id"],
                            "quote": quote,
                            "start": 0,
                            "end": len(quote),
                            "page": None,
                            "match_status": "EXACT",
                        }
                    ],
                }
            ],
            "coverage": {
                "chunks_total": len(chunks),
                "chunks_processed": len(chunks),
                "sections_total": len(sections),
                "sections_processed": len(sections),
            },
            "model_calls": [{"provider": "synthetic-test", "model": "fixture", "outcome": "success"}],
            "warnings": [],
        }

    monkeypatch.setattr(service, "analyze", fake_analyze)
    body = {
        "source_ids": [source["source_id"]],
        "provider": "gemini",
        "consent": True,
        "privacy_mode": "external",
    }
    response = client.post("/api/v1/analyses", json=body, headers={"Idempotency-Key": "test-analysis"})
    assert response.status_code == 202, response.text
    assert (
        client.post("/api/v1/analyses", json=body, headers={"Idempotency-Key": "test-analysis"}).json()
        == response.json()
    )
    ids = response.json()
    assert run_once()
    analysis = client.get("/api/v1/analyses/" + ids["analysis_id"]).json()
    assert analysis["status"] == "COMPLETED", analysis
    findings = client.get("/api/v1/analyses/" + ids["analysis_id"] + "/findings").json()
    assert findings[0]["citations"][0]["source_id"] == source["source_id"]
    with SessionLocal() as db:
        assert db.scalar(select(EvidenceSpan)).quote == "The user must pay invoices within thirty days."
    report = client.get("/api/v1/analyses/" + ids["analysis_id"] + "/exports?format=json")
    assert report.status_code == 200
    assert (
        report.json()["sources"][0]["sha256"]
        == hashlib.sha256(b"The user must pay invoices within thirty days.").hexdigest()
    )
    pdf = client.get("/api/v1/analyses/" + ids["analysis_id"] + "/exports?format=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    report_id = report.headers["X-Report-ID"]
    retained = client.get("/api/v1/exports/" + report_id)
    assert retained.status_code == 200 and retained.content == report.content
    saved = client.get("/api/v1/analyses/" + ids["analysis_id"] + "/reports")
    assert saved.status_code == 200 and len(saved.json()) == 2
    monkeypatch.setattr(
        service,
        "ask",
        lambda *a, **kw: {
            "answer": "Fixture answer",
            "citations": findings[0]["citations"],
            "limitations": [],
        },
    )
    assert (
        client.post(
            "/api/v1/analyses/" + ids["analysis_id"] + "/questions", json={"question": "When must I pay?"}
        ).status_code
        == 200
    )
    assert len(client.get("/api/v1/analyses/" + ids["analysis_id"] + "/questions").json()) == 1
    assert client.delete("/api/v1/sources/" + source["source_id"]).status_code == 204
    assert client.get("/api/v1/analyses/" + ids["analysis_id"]).status_code == 404
    with SessionLocal() as db:
        assert not db.scalars(select(Finding)).all()


def test_expired_lease_is_not_automatically_rebilled(client):
    user = login_guest(client)
    with SessionLocal() as db:
        job = Job(
            owner_id=user["id"],
            kind="analysis",
            state="PROCESSING",
            lease_until=now() - timedelta(minutes=1),
            lease_token="old",
        )
        db.add(job)
        db.commit()
        ident = job.id
    assert not run_once()
    result = client.get("/api/v1/jobs/" + ident).json()
    assert result["state"] == "FAILED"
    assert "calls may have completed" in result["error"]


def test_ingestion_and_discovery_idempotency(client):
    login_guest(client)
    body = {"name": "Agreement", "text": "You must pay invoices."}
    first = client.post("/api/v1/sources/text", json=body, headers={"Idempotency-Key": "source-once"})
    assert first.status_code == 202
    again = client.post("/api/v1/sources/text", json=body, headers={"Idempotency-Key": "source-once"})
    assert again.json() == first.json()
    assert (
        client.post(
            "/api/v1/sources/text",
            json={**body, "text": "Different"},
            headers={"Idempotency-Key": "source-once"},
        ).status_code
        == 409
    )
    assert run_once()
    assert len(client.get("/api/v1/sources").json()) == 1
    first = client.post(
        "/api/v1/discovery",
        json={"url": "https://example.com"},
        headers={"Idempotency-Key": "discovery-once"},
    )
    again = client.post(
        "/api/v1/discovery",
        json={"url": "https://example.com"},
        headers={"Idempotency-Key": "discovery-once"},
    )
    assert first.status_code == 202 and again.json() == first.json()


def test_unreadable_pages_never_get_unqualified_supported_status(client, monkeypatch):
    import app.services.analysis as service

    login_guest(client)
    result = upload_text(client)
    with SessionLocal() as db:
        source = db.get(Source, result["source_id"])
        source.details = {
            **source.details,
            "coverage": {"pages_total": 2, "pages_extracted": 1, "warnings": ["Page 2 unreadable"]},
        }
        db.commit()
    cfg = settings()
    monkeypatch.setattr(cfg, "gemini_api_key", "test-key")
    monkeypatch.setattr(cfg, "gemini_model", "test-model")
    monkeypatch.setattr(
        service,
        "analyze",
        lambda *a: {
            "findings": [
                {
                    "category": "RIGHT",
                    "statement": "Unqualified",
                    "support_status": "SUPPORTED",
                    "citations": [
                        {
                            "source_id": a[1][0]["source_id"],
                            "section_id": a[1][0]["id"],
                            "quote": a[1][0]["text"],
                            "start": 0,
                            "end": len(a[1][0]["text"]),
                            "page": a[1][0].get("page"),
                            "match_status": "EXACT",
                        }
                    ],
                }
            ],
            "coverage": {"chunks_total": 1, "chunks_processed": 1},
            "warnings": [],
        },
    )
    response = client.post(
        "/api/v1/analyses",
        json={
            "source_ids": [result["source_id"]],
            "provider": "gemini",
            "consent": True,
            "privacy_mode": "external",
        },
    )
    assert response.status_code == 202
    assert run_once()
    ident = response.json()["analysis_id"]
    assert client.get("/api/v1/analyses/" + ident).json()["status"] == "PARTIAL_COMPLETION"
    findings = client.get("/api/v1/analyses/" + ident + "/findings").json()
    assert findings[0]["support_status"] == "AMBIGUOUS"


def test_openapi_snapshot_and_typed_response_contracts():
    from app.main import app

    snapshot = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
    assert json.loads(snapshot.read_text(encoding="utf-8")) == app.openapi()
    schemas = app.openapi()["components"]["schemas"]
    assert "SourceResponse" in schemas
    assert "FindingResponse" in schemas
    assert "AnalysisResponse" in schemas
