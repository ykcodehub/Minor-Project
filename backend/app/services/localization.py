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
    canonical = [
        {
            k: f.get(k)
            for k in (
                "id",
                "finding_id",
                "statement",
                "rationale",
                "qualifications",
                "support_status",
                "citations",
            )
        }
        for f in findings
    ]
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fingerprint_candidates(findings):
    """Read exact legacy hashes without re-billing or trusting a different source."""
    legacy = [findings, [{k: v for k, v in f.items() if k != "risk_assessment"} for f in findings]]
    return list(
        dict.fromkeys(
            [
                fingerprint(findings),
                *[
                    hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    for value in legacy
                ],
            ]
        )
    )


def _localize_batch(findings, language, providers):
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


def localize(findings, language, providers):
    """Verified small batches; completed batches survive a later provider failure."""
    from app.providers.base import budget_available_configs, configured_provider

    adapters = [
        configured_provider(p)
        for p in budget_available_configs(providers)
        if p.get("name") in {"gemini", "groq", "openai", "openrouter"}
    ]
    if len(findings) > 200:
        raise ProviderError("TRANSLATION_BUDGET_EXCEEDED")
    pending = [findings[i : i + 4] for i in range(0, len(findings), 4)]
    result, calls = {}, []
    while pending:
        batch = pending.pop(0)
        # Conservative full envelope estimate includes a same-length translated
        # copy for the fidelity operation; actual outbound guards remain final.
        estimated = json.dumps(
            [{k: f.get(k) for k in ("id", "statement", "rationale", "qualifications")} for f in batch],
            ensure_ascii=False,
        )
        if (
            adapters
            and not any(
                p.fits(
                    SYSTEM + directive(language),
                    estimated * 3 + " Translation fidelity and caveats. " * 20,
                    Translations.model_json_schema(),
                    role="explanation_translation",
                )
                for p in adapters
            )
            and len(batch) > 1
        ):
            mid = len(batch) // 2
            pending[:0] = [batch[:mid], batch[mid:]]
            continue
        try:
            values, new_calls = _localize_batch(batch, language, providers)
            result.update(values)
            calls.extend(new_calls)
        except ProviderError as exc:
            calls.extend(exc.model_calls)
            if (
                exc.code in {"PROVIDER_OUTPUT_LIMIT", "PROVIDER_INVALID_OUTPUT", "PROVIDER_CONTEXT_LIMIT"}
                and len(batch) > 1
            ):
                mid = len(batch) // 2
                pending[:0] = [batch[:mid], batch[mid:]]
                continue
            exc.model_calls = calls
            exc.translations = result
            raise
    return result, calls


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
