"""Versioned conservative attention rules, not a legal or company-risk score."""

import re

from app.services.verification import verify_quote

RULE_VERSION = "attention-1.0"
HIGH = re.compile(
    r"\b(?:unlimited liability|irrevocable (?:license|licence)|waive (?:all |any )?(?:rights?|claims?)|sell your personal (?:data|information))\b",
    re.IGNORECASE,
)


def summarize(findings, sections, coverage, state):
    groups = {k: [] for k in ("benefits", "obligations", "restrictions", "potential_risks", "exceptions")}
    mapping = {
        "RIGHT": "benefits",
        "PERMISSION": "benefits",
        "OBLIGATION": "obligations",
        "PAYMENT": "obligations",
        "RESTRICTION": "restrictions",
        "RISK_NOTE": "potential_risks",
        "EXCEPTION": "exceptions",
    }
    valid = []
    for f in findings:
        citations = f.get("citations", [])
        if f.get("support_status") != "SUPPORTED" or not citations:
            continue
        if any(verify_quote(c, sections)["match_status"] not in {"EXACT", "NORMALIZED"} for c in citations):
            continue
        valid.append(f)
        key = mapping.get(f["category"])
        if key:
            groups[key].append(f)
        if f.get("qualifications") and key != "exceptions":
            groups["exceptions"].append(f)
    incomplete = (
        len(valid) != len(findings)
        or state != "COMPLETED"
        or not valid
        or any(f.get("support_status") != "SUPPORTED" for f in findings)
        or coverage.get("warnings")
        or coverage.get("failed_chunks")
        or not coverage.get("chunks_total")
        or coverage.get("chunks_processed", 0) != coverage.get("chunks_total")
        or coverage.get("sections_processed", 0) != coverage.get("sections_total", 0)
        or any(
            s.get("pages_extracted", 0) < s.get("pages_total", 0)
            for s in coverage.get("sources", {}).values()
        )
    )

    def positive_trigger(finding):
        if finding["category"] not in {"RISK_NOTE", "RESTRICTION", "OBLIGATION"}:
            return False
        for citation in finding["citations"]:
            for match in HIGH.finditer(citation["quote"]):
                if not re.search(
                    r"\b(?:no|not|never|without)\b",
                    citation["quote"][max(0, match.start() - 50) : match.start()],
                    re.IGNORECASE,
                ):
                    return True
        return False

    triggers = [f for f in valid if positive_trigger(f)]
    if incomplete:
        level, rule = (
            "Not Determinable",
            "Insufficient coverage, no supported findings, or unresolved interpretations.",
        )
    elif triggers:
        level, rule = (
            "High",
            "Supported source includes an explicit unlimited-liability, irrevocable-license, rights-waiver or personal-data-sale phrase; review its scope and exceptions.",
        )
    elif groups["restrictions"] or groups["potential_risks"] or groups["obligations"]:
        level, rule = (
            "Moderate",
            "Supported restrictions, obligations or risk notes require attention; no high-attention phrase matched.",
        )
    elif all(f["category"] in {"RIGHT", "PERMISSION", "EXCEPTION"} for f in valid):
        level, rule = (
            "Low",
            "Complete processed scope contains supported findings and no classified obligation, restriction, risk note or high-attention phrase. This does not establish safety or absence of undiscovered terms.",
        )
    else:
        level, rule = "Not Determinable", "Supported categories do not justify a rule-based assessment."
    return {
        "level": level,
        "rule": rule,
        "rule_version": RULE_VERSION,
        "groups": {k: v[:8] for k, v in groups.items()},
        "trigger_finding_ids": [f["id"] for f in triggers],
        "disclaimer": "Rule-based document attention only; not legal risk, enforceability, or evidence of a company's real-world practices.",
    }


def suggested_questions(findings, language="en"):
    """Question templates selected only by actual supported categories; no model call or invented terms."""
    templates = {
        "en": [
            ({"OBLIGATION", "PAYMENT"}, "What obligations and payment conditions does this document state?"),
            ({"RIGHT", "PERMISSION"}, "What rights does this document give me?"),
            ({"PRIVACY", "CONSENT"}, "What does this document say about data sharing and consent?"),
            ({"TERMINATION"}, "What conditions apply to cancellation or termination?"),
            ({"RESTRICTION", "RISK_NOTE"}, "Which restrictions need attention, and what exceptions apply?"),
        ],
        "hi": [
            ({"OBLIGATION", "PAYMENT"}, "दस्तावेज़ में कौन से दायित्व और भुगतान शर्तें हैं?"),
            ({"RIGHT", "PERMISSION"}, "दस्तावेज़ मुझे कौन से अधिकार देता है?"),
            ({"PRIVACY", "CONSENT"}, "दस्तावेज़ डेटा साझा करने और सहमति के बारे में क्या कहता है?"),
            ({"TERMINATION"}, "रद्द करने या समाप्ति पर कौन सी शर्तें लागू हैं?"),
            ({"RESTRICTION", "RISK_NOTE"}, "किन प्रतिबंधों पर ध्यान देना चाहिए और क्या अपवाद हैं?"),
        ],
        "hinglish": [
            ({"OBLIGATION", "PAYMENT"}, "Document mein meri kya duties aur payment conditions hain?"),
            ({"RIGHT", "PERMISSION"}, "Document mujhe kaun se rights deta hai?"),
            ({"PRIVACY", "CONSENT"}, "Document data sharing aur consent ke baare mein kya kehta hai?"),
            ({"TERMINATION"}, "Cancel ya terminate karne par kya conditions hain?"),
            ({"RESTRICTION", "RISK_NOTE"}, "Kaun si restrictions par dhyan doon aur kya exceptions hain?"),
        ],
    }
    categories = {
        f["category"]
        for f in findings
        if f.get("support_status") == "SUPPORTED"
        and f.get("citations")
        and all(c.get("match_status") in {"EXACT", "NORMALIZED"} for c in f["citations"])
    }
    return [question for group, question in templates[language] if categories & group][:3]
