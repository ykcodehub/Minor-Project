"""Real extraction/chunking/DB/citations; AI and public URL boundary synthetic, never paid."""

from hashlib import sha256
from io import BytesIO

import pytest
from sqlalchemy import select
from test_api import register

from app.config import settings
from app.db import SessionLocal
from app.models import EvidenceSpan, Job
from app.worker import run_once

TEXT = "The user must pay invoices within thirty days."


@pytest.fixture
def ai(monkeypatch):
    import app.services.analysis as service

    cfg = settings()
    monkeypatch.setattr(cfg, "gemini_api_key", "synthetic-only")
    monkeypatch.setattr(cfg, "gemini_model", "synthetic-model")

    def analyze(chunks, sections, providers, on_progress):
        section = max(sections, key=lambda s: len(s["text"]))
        quote = section["text"]
        on_progress("VERIFYING", 1, 1)
        return {
            "findings": [
                {
                    "category": "OBLIGATION",
                    "statement": TEXT,
                    "rationale": "Synthetic boundary fixture only.",
                    "qualifications": [],
                    "support_status": "SUPPORTED",
                    "verification": {"method": "synthetic fixture"},
                    "citations": [
                        {
                            "source_id": section["source_id"],
                            "section_id": section["id"],
                            "quote": quote,
                            "start": 0,
                            "end": len(quote),
                            "page": section.get("page"),
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

    monkeypatch.setattr(service, "analyze", analyze)


def analyze_saved(client, source_id):
    created = client.post(
        "/api/v1/analyses",
        json={"source_ids": [source_id], "provider": "gemini", "consent": True, "privacy_mode": "external"},
    )
    assert created.status_code == 202
    assert run_once()
    analysis_id = created.json()["analysis_id"]
    result = client.get(f"/api/v1/analyses/{analysis_id}")
    assert result.status_code == 200 and result.json()["status"] == "COMPLETED"
    findings = client.get(f"/api/v1/analyses/{analysis_id}/findings").json()
    assert findings and findings[0]["citations"][0]["match_status"] == "EXACT"
    with SessionLocal() as db:
        assert (
            db.scalar(select(EvidenceSpan).where(EvidenceSpan.finding_id == findings[0]["finding_id"]))
            is not None
        )


@pytest.mark.parametrize("format", ["txt", "html", "docx", "pdf"])
def test_formats_ingest_analysis_evidence_and_persistence(client, ai, format):
    register(client)
    data = TEXT.encode()
    if format == "html":
        data = ("<html><h1>Payment</h1><p>" + TEXT + "</p></html>").encode()
    if format == "docx":
        from docx import Document

        document = Document()
        document.add_paragraph(TEXT)
        buffer = BytesIO()
        document.save(buffer)
        data = buffer.getvalue()
    if format == "pdf":
        import pymupdf

        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), TEXT)
        data = document.tobytes()
        document.close()
    response = client.post(
        "/api/v1/sources/upload", files={"file": ("fixture." + format, data, "application/octet-stream")}
    )
    assert response.status_code == 202
    source_id = response.json()["source_id"]
    assert client.get(f"/api/v1/sources/{source_id}").json()["status"] == "QUEUED"
    assert run_once()
    source = client.get(f"/api/v1/sources/{source_id}").json()
    assert source["status"] == "READY" and source["sections"]
    analyze_saved(client, source_id)


def test_pasted_text_and_website_discovery_capture_analysis(client, ai, monkeypatch):
    from app.services import discovery

    register(client)
    pasted = client.post("/api/v1/sources/text", json={"name": "pasted", "text": TEXT}).json()
    assert run_once()
    analyze_saved(client, pasted["source_id"])
    url = "https://example.com/privacy"
    data = ("<html><p>" + TEXT + "</p></html>").encode()
    monkeypatch.setattr(
        discovery,
        "discover",
        lambda _: {
            "candidates": [{"url": url, "status": "ACCESSIBLE", "type": "privacy"}],
            "missing": [],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        discovery,
        "safe_fetch",
        lambda _: {"data": data, "url": url, "mime": "text/html", "sha256": sha256(data).hexdigest()},
    )
    queued = client.post("/api/v1/discovery", json={"url": "https://example.com"}).json()
    assert run_once()
    captured = client.post("/api/v1/sources/url", json={"url": url, "discovery_job_id": queued["job_id"]})
    assert captured.status_code == 202
    assert run_once()
    with SessionLocal() as db:
        assert db.get(Job, captured.json()["job_id"]).state == "COMPLETED"
    analyze_saved(client, captured.json()["source_id"])
