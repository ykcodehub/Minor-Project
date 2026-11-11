"""Versioned conservative attention rules, not a legal or company-risk score."""

import re
from collections import Counter

from app.services.verification import verify_quote

RULE_VERSION = "attention-1.2"
HIGH = re.compile(
    r"\b(?:unlimited liability|irrevocable (?:license|licence)|waive (?:all |any )?(?:rights?|claims?)|sell your personal (?:data|information))\b",
    re.IGNORECASE,
)


def assess_finding(finding, source_validated=False):
    """Ordinal review priority, never probability of legal harm."""
    citations = finding.get("citations", [])
    level, reason = "Needs Review", "The interpretation has not passed source and semantic verification."
    if (
        finding.get("support_status") == "SUPPORTED"
        and citations
        and (source_validated or all(c.get("match_status") in {"EXACT", "NORMALIZED"} for c in citations))
    ):
        high = any(
            not re.search(
                r"\b(?:no|not|never|without)\b", c["quote"][max(0, m.start() - 50) : m.start()], re.IGNORECASE
            )
            for c in citations
            for m in HIGH.finditer(c["quote"])
        )
        if high:
            level, reason = (
                "High",
                "A supported quote contains an explicit high-attention phrase. Review its scope and exceptions.",
            )
        elif finding.get("category") in {
            "OBLIGATION",
            "PAYMENT",
            "RESTRICTION",
            "RISK_NOTE",
            "PRIVACY",
            "CONSENT",
            "TERMINATION",
            "DISPUTE",
        }:
            level, reason = (
                "Moderate",
                "A verified duty, restriction or consequential condition requires review; no high-attention phrase matched.",
            )
        elif finding.get("category") in {"RIGHT", "PERMISSION", "EXCEPTION"}:
            level, reason = (
                "Low",
                "A verified right, permission or exception is lower review priority under these rules; this does not establish safety.",
            )
        else:
            level, reason = "Unassessed", "This verified provision has no applicable severity rule."
    return {"level": level, "reason": reason, "rule_version": RULE_VERSION}


def summarize(findings, sections, coverage, state):
    groups = {
        k: []
        for k in (
            "benefits",
            "obligations",
            "restrictions",
            "potential_risks",
            "exceptions",
            "privacy_consent",
            "termination",
            "disputes",
            "other_clauses",
        )
    }
    mapping = {
        "RIGHT": "benefits",
        "PERMISSION": "benefits",
        "OBLIGATION": "obligations",
        "PAYMENT": "obligations",
        "RESTRICTION": "restrictions",
        "RISK_NOTE": "potential_risks",
        "EXCEPTION": "exceptions",
        "PRIVACY": "privacy_consent",
        "CONSENT": "privacy_consent",
        "TERMINATION": "termination",
        "DISPUTE": "disputes",
        "CLAUSE": "other_clauses",
        "OTHER": "other_clauses",
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
        or any(
            w != "PDF reading order and hidden text cannot be guaranteed; inspect original pages."
            for w in coverage.get("warnings", [])
        )
        or coverage.get("failed_chunks")
        or not coverage.get("chunks_total")
        or coverage.get("chunks_processed", 0) != coverage.get("chunks_total")
        or coverage.get("sections_processed", 0) != coverage.get("sections_total", 0)
        or any(
            s.get("pages_extracted", 0) < s.get("pages_total", 0)
            for s in coverage.get("sources", {}).values()
        )
    )

    assessments = {f.get("finding_id", f.get("id")): assess_finding(f, source_validated=True) for f in valid}
    risk_groups = {
        level: [f for f in valid if assessments[f.get("finding_id", f.get("id"))]["level"] == level]
        for level in ("High", "Moderate", "Low", "Unassessed")
    }
    triggers = risk_groups["High"]
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
    elif risk_groups["Moderate"]:
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
        "risk_groups": risk_groups,
        "risk_counts": {k: len(v) for k, v in risk_groups.items()},
        "assessments": assessments,
        "assessment_complete": not bool(incomplete) and not risk_groups["Unassessed"],
        "priority_index": None
        if incomplete or risk_groups["Unassessed"]
        else (3 if triggers else 2 if risk_groups["Moderate"] else 1),
        "priority_method": "Ordinal review index: Low=1, Moderate=2, High=3; maximum classified verified finding. Available only with complete processed coverage and classification. Not a probability, legal-risk score or guarantee of safety.",
        "coverage": {
            k: coverage.get(k, 0)
            for k in ("chunks_total", "chunks_processed", "sections_total", "sections_processed")
        },
        "counts": {
            "retained": len(findings),
            "verified": len(valid),
            "excluded": len(findings) - len(valid),
            **dict(Counter(f.get("support_status", "AMBIGUOUS") for f in findings)),
        },
        "processing_state": state,
        "overview_findings": valid[:3],
        "unestablished_topics": [key for key, values in groups.items() if not values],
        "group_totals": {key: len(values) for key, values in groups.items()},
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
