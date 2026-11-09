"""Explicit live synthetic AI smoke check; no user documents, secrets or database writes."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import settings
from app.providers.base import ProviderError
from app.services.analysis import analyze, ask
from app.services.chunking import chunk_sections
from app.services.localization import localize


def main():
    provider_name = sys.argv[1] if len(sys.argv) > 1 else "gemini"
    providers = [
        p
        for p in settings().providers()
        if p["name"] == provider_name and p["key"] and p["model"]
    ]
    sections = [
        {
            "id": "synthetic-section",
            "source_id": "synthetic-source",
            "ordinal": 0,
            "page": 1,
            "text": "We share your personal data with third parties only with your consent, except when disclosure is required by law.",
            "heading": "Privacy",
        }
    ]
    chunks = chunk_sections(sections)
    results = {"provider": provider_name}
    try:
        analysis = analyze(chunks, sections, providers)
        findings = analysis["findings"]
        results["supported_findings"] = sum(
            f["support_status"] == "SUPPORTED" for f in findings
        )
        for language in ("hi", "hinglish"):
            try:
                translated, calls = localize(findings, language, providers)
                results["translation_" + language] = {
                    "verified": len(translated) == len(findings) and bool(findings),
                    "calls": len(calls),
                }
            except ProviderError as exc:
                results["translation_" + language] = {"error": exc.code}
        for language in ("en", "hi", "hinglish"):
            try:
                answer = ask(
                    "Kya ye company mera data kisi aur ko share karegi?",
                    findings,
                    sections,
                    providers,
                    retrieved_chunks=chunks,
                    language=language,
                )
                results["answer_" + language] = {
                    "cited": bool(answer["citations"]),
                    "quotes_preserved": all(
                        c["quote"] in sections[0]["text"] for c in answer["citations"]
                    ),
                    "calls": len(answer["model_calls"]),
                }
            except ProviderError as exc:
                results["answer_" + language] = {"error": exc.code}
    except ProviderError as exc:
        results["analysis"] = {
            "error": exc.code,
            "calls": [
                {k: c.get(k) for k in ("outcome", "http_status", "role")}
                for c in exc.model_calls
            ],
        }
    (
        ROOT
        / "docs"
        / "verification-artifacts"
        / ("multilingual-live-" + provider_name + ".json")
    ).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
