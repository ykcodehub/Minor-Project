"""Final acceptance-fixture integrity and interrupted-worker preservation; no inference."""

import json
import runpy
from pathlib import Path

from conftest import login_guest
from sqlalchemy import select
from test_api import upload_text

from app import worker
from app.config import settings
from app.db import SessionLocal
from app.models import EvidenceSpan, Finding, Section
from app.services import analysis as a
from app.services.ingest import extract


def test_final_live_fixture_has_six_complete_clauses_on_two_pages(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    harness = runpy.run_path(str(scripts / "final_live_acceptance.py"))
    result = extract(harness["synthetic_pdf"](), "synthetic.pdf")
    assert result["coverage"]["pages_total"] == result["coverage"]["pages_extracted"] == 2
    text = " ".join(s["text"] for s in result["sections"])
    normalized = " ".join(text.split())
    assert len(harness["CLAUSES"]) == 6
    assert all(clause in normalized for clause in harness["CLAUSES"])


def test_verified_finding_survives_later_unexpected_worker_failure(client, monkeypatch):
    login_guest(client)
    first = "Invoices must be paid within thirty days."
    source = upload_text(client, first + "\n\nCustomer may request a copy of stored records.")
    monkeypatch.setattr(settings(), "groq_api_key", "synthetic")
    monkeypatch.setattr(settings(), "groq_model", "synthetic")
    reviews = 0

    def generate(configs, system, prompt, schema, role):
        nonlocal reviews
        calls = [{"provider": "groq", "model": "synthetic", "outcome": "SUCCESS"}]
        if role == "candidate_generation":
            passages = json.loads(prompt[prompt.index("[") :])
            return a.CandidateBatch(
                findings=[
                    {
                        "source_id": p["source_id"],
                        "section_id": p["section_id"],
                        "page": p["page"],
                        "quote": p["text"],
                        "start": p["start_offset"],
                        "end": p["end_offset"],
                        "category": "PAYMENT",
                        "statement": p["text"],
                        "rationale": "Controlled fixture",
                        "qualifications": [],
                        "cross_references": [],
                    }
                    for p in passages
                ]
            ), calls
        reviews += 1
        if reviews > 1:
            raise RuntimeError("Controlled interruption; no model request")
        return a.Verdict(
            support_status="SUPPORTED",
            rationale="Controlled entailment.",
            missing_qualifiers=[],
            unresolved_references=[],
            category_consistent=True,
        ), calls

    monkeypatch.setattr(a, "generate_with_fallback", generate)
    created = client.post(
        "/api/v1/analyses",
        json={
            "source_ids": [source["source_id"]],
            "provider": "groq",
            "consent": True,
            "privacy_mode": "external",
        },
    )
    assert created.status_code == 202 and worker.run_once()
    aid, jid = created.json()["analysis_id"], created.json()["job_id"]
    job = client.get(f"/api/v1/jobs/{jid}").json()
    assert job["state"] == job["stage"] == "PARTIAL_COMPLETION"
    findings = client.get(f"/api/v1/analyses/{aid}/findings").json()
    assert len(findings) == 1 and findings[0]["support_status"] == "SUPPORTED"
    assert findings[0]["citations"][0]["quote"].rstrip() == first
    with SessionLocal() as db:
        assert db.scalar(select(EvidenceSpan)).quote == findings[0]["citations"][0]["quote"]
        stored = db.scalar(select(Finding))
        original_id = stored.id
        sections = [s.data for s in db.scalars(select(Section))]
        replay = dict(stored.data)
        replay["id"] = "different-server-attempt-id"
        worker.save_finding(db, aid, replay, sections, [source["source_id"]])
        db.commit()
        assert db.scalars(select(Finding.id)).all() == [original_id]
        assert len(db.scalars(select(EvidenceSpan)).all()) == 1
    summary = client.get(f"/api/v1/analyses/{aid}/summary").json()["summary"]
    assert summary["counts"]["verified"] == 1 and summary["level"] == "Not Determinable"
