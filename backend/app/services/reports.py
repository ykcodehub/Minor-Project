"""Localized printable reports; authoritative source text is escaped and preserved."""

from html import escape

LABELS = {
    "hi": {
        "DOCUMENT ANALYSIS / EVIDENCE REPORT": "दस्तावेज़ विश्लेषण / साक्ष्य रिपोर्ट",
        "Analysis": "विश्लेषण",
        "Captured report scope": "रिपोर्ट का समय",
        "Analysis state": "विश्लेषण स्थिति",
        "Scope and limitations": "दायरा और सीमाएँ",
        "Captured sources": "संग्रहित स्रोत",
        "Version": "संस्करण",
        "Acquired": "संग्रह समय",
        "Origin": "मूल स्रोत",
        "Processing coverage": "प्रसंस्करण कवरेज",
        "Findings and Evidence Passports": "निष्कर्ष और साक्ष्य विवरण",
        "Source": "स्रोत",
        "Section": "अनुभाग",
        "Page": "पृष्ठ",
        "Unicode offsets": "यूनिकोड स्थान",
        "Citation validity": "उद्धरण वैधता",
        "Qualifications": "शर्तें और अपवाद",
        "Verifier": "समीक्षक",
        "Review rationale": "समीक्षा कारण",
        "Model": "मॉडल",
        "Prompt version": "प्रॉम्प्ट संस्करण",
        "Integrity notice": "अखंडता सूचना",
        "Verified against source": "स्रोत से समर्थित",
        "None recorded": "दर्ज नहीं",
        "Not available": "उपलब्ध नहीं",
        "No findings were generated. This does not establish that the source has no relevant provisions.": "कोई निष्कर्ष नहीं मिला। इससे यह सिद्ध नहीं होता कि स्रोत में संबंधित प्रावधान नहीं हैं।",
        "A document digest identifies captured bytes. It does not prove origin authenticity, real-world conduct, enforceability or court admissibility. Keep the JSON manifest alongside this report for machine-readable metadata.": "दस्तावेज़ हैश संग्रहित बाइट की पहचान करता है। यह स्रोत की प्रामाणिकता, वास्तविक व्यवहार, कानूनी प्रवर्तनीयता या न्यायालय में स्वीकार्यता का प्रमाण नहीं है। मशीन-पठनीय विवरण के लिए JSON मैनिफेस्ट साथ रखें।",
    },
    "hinglish": {
        "DOCUMENT ANALYSIS / EVIDENCE REPORT": "Document analysis / evidence report",
        "Analysis": "Analysis",
        "Captured report scope": "Report capture ka samay",
        "Analysis state": "Analysis ki state",
        "Scope and limitations": "Scope aur limitations",
        "Captured sources": "Captured sources",
        "Version": "Version",
        "Acquired": "Capture ka samay",
        "Origin": "Original source",
        "Processing coverage": "Processing ki coverage",
        "Findings and Evidence Passports": "Findings aur Evidence Passports",
        "Source": "Source",
        "Section": "Section",
        "Page": "Page",
        "Unicode offsets": "Unicode offsets",
        "Citation validity": "Citation ki validity",
        "Qualifications": "Shartein aur exceptions",
        "Verifier": "Verifier",
        "Review rationale": "Review ka reason",
        "Model": "Model",
        "Prompt version": "Prompt version",
        "Integrity notice": "Integrity notice",
        "Verified against source": "Source se supported",
        "None recorded": "Koi record nahi",
        "Not available": "Available nahi",
        "No findings were generated. This does not establish that the source has no relevant provisions.": "Koi finding generate nahi hui. Isse source mein relevant terms na hona prove nahi hota.",
        "A document digest identifies captured bytes. It does not prove origin authenticity, real-world conduct, enforceability or court admissibility. Keep the JSON manifest alongside this report for machine-readable metadata.": "Document hash captured bytes identify karta hai. Ye origin authenticity, actual behaviour, enforceability ya court admissibility prove nahi karta. Machine-readable metadata ke liye JSON manifest saath rakhein.",
    },
}


def report_html(manifest):
    labels = LABELS.get(manifest.get("language", "en"), {})

    def t(value):
        return labels.get(value, value)

    def safe(value):
        return escape(str(value if value is not None else t("Not available")))

    def field(label, value):
        return f"{safe(t(label))}: {safe(value)}<br>"

    parts = [
        f"<h1>VERIORA</h1><p class='eyebrow'>{safe(t('DOCUMENT ANALYSIS / EVIDENCE REPORT'))}</p>",
        "<p>"
        + field("Analysis", manifest["analysis_id"])
        + field("Captured report scope", manifest["created_at"])
        + field("Analysis state", manifest["status"])
        + "</p>",
        f"<h2>{safe(t('Scope and limitations'))}</h2><ul>",
    ]
    from app.services.language import LIMITATIONS

    limitations = (
        manifest["limitations"]
        if manifest.get("language", "en") == "en"
        else list(dict.fromkeys(LIMITATIONS[manifest["language"]] + manifest["limitations"]))
    )
    parts += [f"<li>{safe(item)}</li>" for item in limitations]
    parts += [f"</ul><h2>{safe(t('Captured sources'))}</h2>"]
    for source in manifest["sources"]:
        parts += [
            f"<h3>{safe(source['original_name'])}</h3><p>"
            + field("Version", source["id"])
            + field("Acquired", source["captured_at"])
            + field("Origin", source.get("source_url") or source["kind"])
            + f"SHA-256:<br><span class='hash'>{safe(source['sha256'][:32])}<br>{safe(source['sha256'][32:])}</span></p>"
        ]
    parts += [f"<h2>{safe(t('Processing coverage'))}</h2><ul>"]
    parts += [
        f"<li>{safe(key.replace('_', ' '))}: {safe(value)}</li>"
        for key, value in manifest["coverage"].items()
    ]
    parts += [f"</ul><h2>{safe(t('Findings and Evidence Passports'))}</h2>"]
    if not manifest["findings"]:
        parts.append(
            f"<p>{safe(t('No findings were generated. This does not establish that the source has no relevant provisions.'))}</p>"
        )
    for index, finding in enumerate(manifest["findings"], 1):
        verified = (
            finding.get("support_status") == "SUPPORTED"
            and finding.get("citations")
            and all(c.get("match_status") in {"EXACT", "NORMALIZED"} for c in finding["citations"])
        )
        status = t("Verified against source") if verified else finding.get("support_status", "AMBIGUOUS")
        parts += [
            f"<h3>{index}. {safe(finding['statement'])}</h3><p><b>{safe(status)}</b> / {safe(finding['category'])}<br>Finding: {safe(finding.get('finding_id'))}</p><p>{safe(finding.get('rationale'))}</p>"
        ]
        for citation in finding.get("citations", []):
            parts += [
                f"<blockquote>{safe(citation['quote'])}</blockquote><p>"
                + field("Source", citation["source_id"])
                + field("Section", citation["section_id"])
                + field("Page", citation.get("page"))
                + field("Unicode offsets", f"{citation['start']}–{citation['end']}")
                + field("Citation validity", citation.get("match_status"))
                + "</p>"
            ]
        parts += [
            "<p>"
            + field("Qualifications", "; ".join(finding.get("qualifications", [])) or t("None recorded"))
            + field("Verifier", finding.get("verification", {}).get("method"))
            + field("Review rationale", finding.get("verification", {}).get("rationale"))
            + field("Model", str(finding.get("provider")) + " / " + str(finding.get("model")))
            + field("Prompt version", finding.get("prompt_version"))
            + "</p>"
        ]
    parts += [
        f"<h2>{safe(t('Integrity notice'))}</h2><p>{safe(t('A document digest identifies captured bytes. It does not prove origin authenticity, real-world conduct, enforceability or court admissibility. Keep the JSON manifest alongside this report for machine-readable metadata.'))}</p>"
    ]
    return "".join(parts)
