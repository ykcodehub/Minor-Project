"""Build the explicitly authored offline fixture; never call AI or a database."""

import hashlib
import json
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ingest import extract
from app.services.summary import assess_finding, summarize
from app.services.verification import verify_quote

# Authored expectations, not model output or independent legal review.
CLAUSES = [
    (
        "RISK_NOTE",
        "The customer accepts unlimited liability for all service losses.",
        "ग्राहक सभी सेवा हानियों के लिए असीमित दायित्व स्वीकार करता है।",
        "Customer sabhi service losses ke liye unlimited liability accept karta hai.",
    ),
    (
        "RESTRICTION",
        "The customer grants an irrevocable license to submitted materials.",
        "ग्राहक जमा सामग्री का अपरिवर्तनीय लाइसेंस देता है।",
        "Customer submitted materials ka irrevocable license deta hai.",
    ),
    (
        "PAYMENT",
        "Invoices must be paid within thirty days.",
        "बिलों का भुगतान तीस दिनों के भीतर करना होगा।",
        "Invoices ka payment tees din ke andar karna hoga.",
    ),
    (
        "PRIVACY",
        "Personal data may be shared with service providers only with consent.",
        "व्यक्तिगत डेटा केवल सहमति से सेवा प्रदाताओं के साथ साझा किया जा सकता है।",
        "Personal data sirf consent ke saath service providers ko share kiya ja sakta hai.",
    ),
    (
        "TERMINATION",
        "The supplier may terminate service on seven days notice.",
        "आपूर्तिकर्ता सात दिनों की सूचना पर सेवा समाप्त कर सकता है।",
        "Supplier saat din ke notice par service terminate kar sakta hai.",
    ),
    (
        "DISPUTE",
        "Disputes must be resolved by arbitration in the stated venue.",
        "विवाद निर्धारित स्थान पर मध्यस्थता द्वारा सुलझाए जाने चाहिए।",
        "Disputes stated venue par arbitration se resolve karne honge.",
    ),
    (
        "RIGHT",
        "The customer may request a copy of their stored records.",
        "ग्राहक अपने संग्रहीत रिकॉर्ड की प्रति माँग सकता है।",
        "Customer apne stored records ki copy maang sakta hai.",
    ),
]


def build():
    doc = pymupdf.open()
    for page_number, rows in enumerate((CLAUSES[:4], CLAUSES[4:])):
        page = doc.new_page()
        page.insert_text((35, 45), f"SYNTHETIC DEMO AGREEMENT - Page {page_number + 1}", fontsize=12)
        for i, (_, quote, _, _) in enumerate(rows):
            page.insert_text((35, 100 + i * 65), quote, fontsize=8)
    pdf = doc.tobytes(garbage=4, deflate=True, no_new_id=True)
    doc.close()
    extracted = extract(pdf, "synthetic-demo-agreement.pdf")
    sections = extracted["sections"]
    findings, translations = [], {"hi": {}, "hinglish": {}}
    for index, (category, quote, hi, hinglish) in enumerate(CLAUSES):
        section = next(s for s in sections if quote in s["text"])
        # Stable public fixture identifiers, never identifiers of private records.
        for ordinal, item in enumerate(sections):
            item.update(id=f"demo-section-{ordinal}", source_id="offline-synthetic")
        start = section["text"].index(quote)
        citation = {
            "source_id": "offline-synthetic",
            "section_id": section["id"],
            "page": section["page"],
            "quote": quote,
            "start": start,
            "end": start + len(quote),
        }
        checked = verify_quote(citation, sections)
        assert checked["match_status"] == "EXACT"
        citation["match_status"] = "EXACT"
        finding = {
            "id": f"demo-finding-{index}",
            "finding_id": f"demo-finding-{index}",
            "category": category,
            "statement": quote,
            "rationale": "Authored reference annotation restates the exact synthetic clause.",
            "support_status": "SUPPORTED",
            "qualifications": [],
            "citations": [citation],
            "verification": {"method": "authored_reference_exact_quote_check", "live_model_review": False},
        }
        finding["risk_assessment"] = assess_finding(finding)
        findings.append(finding)
        for lang, statement in (("hi", hi), ("hinglish", hinglish)):
            translations[lang][finding["finding_id"]] = {
                "statement": statement,
                "rationale": statement,
                "qualifications": [],
            }
    coverage = {"sections_total": len(sections), "sections_processed": len(sections)}
    summary = summarize(findings, sections, coverage, "COMPLETED")
    return pdf, {
        "mode": "OFFLINE_AUTHORED_REFERENCE",
        "version": "1",
        "live_inference": False,
        "provenance": "Authored synthetic reference. Exact quotations and risk rules validated locally; no live or independent semantic verification.",
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "pages": 2,
        "sections": sections,
        "findings": findings,
        "summary": summary,
        "translations": translations,
    }


if __name__ == "__main__":
    pdf, data = build()
    assets = ROOT / "frontend/public/demo"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "synthetic-agreement.pdf").write_bytes(pdf)
    target = ROOT / "frontend/src/demo/synthetic-agreement.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Offline authored reference built: 2 pages; 7 exact quotations; no AI/database access.")
