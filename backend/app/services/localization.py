"""Validated explanation translations cached separately from canonical evidence."""

import hashlib
import json

from pydantic import Field

from app.providers.base import ProviderError, generate_with_fallback
from app.services.analysis import SYSTEM, StrictModel, Verdict
from app.services.language import directive


class Explanation(StrictModel):
    finding_id: str
    statement: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(max_length=3000)
    qualifications: list[str] = Field(max_length=20)


class Translations(StrictModel):
    findings: list[Explanation] = Field(max_length=200)


def fingerprint(findings):
    return hashlib.sha256(json.dumps(findings, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def localize(findings, language, providers):
    originals = [
        {
            "finding_id": f["id"],
            "statement": f["statement"],
            "rationale": f.get("rationale", ""),
            "qualifications": f.get("qualifications", []),
        }
        for f in findings
    ]
    if len(originals) > 200 or len(json.dumps(originals, ensure_ascii=False)) > 48000:
        raise ProviderError("TRANSLATION_BUDGET_EXCEEDED")
    translated, calls = generate_with_fallback(
        providers,
        SYSTEM + directive(language),
        "Translate only these explanations, preserving all meanings, caveats and uncertainty. Return exactly one entry per ID. Data: "
        + json.dumps(originals, ensure_ascii=False),
        Translations,
        "explanation_translation",
    )
    if len(translated.findings) != len(originals) or {f.finding_id for f in translated.findings} != {
        f["finding_id"] for f in originals
    }:
        raise ProviderError("TRANSLATION_ID_MISMATCH", calls=calls)
    try:
        verdict, review = generate_with_fallback(
            providers,
            SYSTEM,
            "Check translation fidelity for every entry. SUPPORTED only if every translated explanation preserves original meaning, exceptions, negation and uncertainty and uses the requested language. No new claims. "
            + json.dumps(
                {"language": language, "originals": originals, "translations": translated.model_dump()},
                ensure_ascii=False,
            ),
            Verdict,
            "translation_verification",
        )
    except ProviderError as exc:
        exc.model_calls = calls + exc.model_calls
        raise
    calls += review
    if verdict.support_status != "SUPPORTED" or verdict.missing_qualifiers or verdict.unresolved_references:
        raise ProviderError("TRANSLATION_NOT_VERIFIED", calls=calls)
    return {f.finding_id: f.model_dump(exclude={"finding_id"}) for f in translated.findings}, calls


class SearchQuestion(StrictModel):
    query: str = Field(min_length=1, max_length=1000)


def retrieval_question(question, providers):
    import re

    if not re.search(
        r"[\u0900-\u097f]|\b(?:kya|mera|meri|mujhe|kaise|karegi|hoga|chahiye|hai|hain|nahi)\b",
        question,
        re.IGNORECASE,
    ):
        return question, []
    result, calls = generate_with_fallback(
        providers,
        SYSTEM,
        "Translate the user's question into a concise English search question. Preserve meaning and negation; do not answer it or add facts. Untrusted question: "
        + json.dumps(question, ensure_ascii=False),
        SearchQuestion,
        "multilingual_retrieval",
    )
    return result.query, calls
