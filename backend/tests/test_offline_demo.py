"""Validate the public authored fixture against its actual PDF; no mocked inference."""

import hashlib
import json
from pathlib import Path

from app.services.ingest import extract
from app.services.summary import summarize
from app.services.verification import verify_quote

ROOT = Path(__file__).resolve().parents[2]


def test_offline_reference_has_exact_quotes_pages_hash_and_honest_provenance():
    data = json.loads((ROOT / "frontend/src/demo/synthetic-agreement.json").read_text(encoding="utf-8"))
    pdf = (ROOT / "frontend/public/demo/synthetic-agreement.pdf").read_bytes()
    actual = extract(pdf, "synthetic.pdf")
    assert actual["coverage"]["pages_total"] == 2
    assert hashlib.sha256(pdf).hexdigest() == data["sha256"]
    assert data["mode"] == "OFFLINE_AUTHORED_REFERENCE" and data["live_inference"] is False
    assert [s["text"] for s in actual["sections"]] == [s["text"] for s in data["sections"]]
    for finding in data["findings"]:
        assert finding["verification"]["live_model_review"] is False
        for citation in finding["citations"]:
            assert verify_quote(citation, data["sections"])["match_status"] == "EXACT"
            section = next(s for s in data["sections"] if s["id"] == citation["section_id"])
            assert section["page"] == citation["page"]
            assert section["text"][citation["start"] : citation["end"]] == citation["quote"]
    coverage = {"sections_total": len(data["sections"]), "sections_processed": len(data["sections"])}
    summary = summarize(data["findings"], data["sections"], coverage, "COMPLETED")
    assert summary["risk_counts"] == {"High": 2, "Moderate": 4, "Low": 1, "Unassessed": 0}
    assert summary["risk_counts"] == data["summary"]["risk_counts"]
    for language in ("hi", "hinglish"):
        assert set(data["translations"][language]) == {f["finding_id"] for f in data["findings"]}
