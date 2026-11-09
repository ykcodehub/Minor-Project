"""Presentation language only: authoritative evidence bytes are never translated."""

LANGUAGES = {
    "en": "English",
    "hi": "Hindi (Devanagari)",
    "hinglish": "Hinglish (natural Hindi in Latin script mixed with English)",
}
ABSTENTION = {
    "en": "I cannot confirm this from the available document.",
    "hi": "उपलब्ध दस्तावेज़ से मैं इसकी पुष्टि नहीं कर सकता।",
    "hinglish": "Available document se main is baat ki pushti nahi kar sakta.",
}


def directive(language):
    if language not in LANGUAGES:
        raise ValueError("Unsupported language")
    return (
        " Write explanations, answers and caveats in "
        + LANGUAGES[language]
        + ". Preserve every original evidence quote, source ID, page, offset, category and status exactly. "
        "Understand questions in English, Hindi or informal Hinglish, regardless of answer language."
    )


LIMITATIONS = {
    "en": [
        "Answers describe the captured document, not actual company conduct or legal advice.",
        "Only available selected sources were reviewed; AI review can make mistakes.",
    ],
    "hi": [
        "उत्तर दस्तावेज़ में लिखी बातों पर आधारित हैं, कंपनी के वास्तविक व्यवहार या कानूनी सलाह पर नहीं।",
        "केवल उपलब्ध चुने हुए स्रोतों की समीक्षा की गई है। AI समीक्षा में त्रुटियाँ हो सकती हैं।",
    ],
    "hinglish": [
        "Jawab captured document par based hai, company ke actual behaviour ya legal advice par nahi.",
        "Sirf available selected sources review hue hain. AI review mein galti ho sakti hai.",
    ],
}
