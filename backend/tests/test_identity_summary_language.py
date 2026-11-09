"""New features: real token lifecycle, OIDC cryptography, source integrity and language safety."""

from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from test_ai import CHUNKS, SECTIONS
from test_api import register

from app.config import settings
from app.db import SessionLocal
from app.models import PendingRegistration, User, now
from app.security import digest
from app.services import analysis, identity
from app.services.language import ABSTENTION
from app.services.summary import summarize

DATA = {"email": "new@example.com", "password": "Ownership-password-2026!"}


def signup(client):
    cfg = settings()
    with (
        patch.object(cfg, "smtp_host", "capture.invalid"),
        patch.object(cfg, "mail_from", "sender@example.com"),
    ):
        response = client.post("/api/v1/auth/register", json=DATA)
    assert response.status_code == 202
    return client.veriora_mail[-1]["token"]


def test_pending_registration_requires_mail_ownership_password_and_single_use(client):
    token = signup(client)
    with SessionLocal() as db:
        assert not db.scalar(select(User).where(User.email == DATA["email"]))
        pending = db.get(PendingRegistration, digest(token))
        assert pending and token not in pending.password_hash and pending.password_hash != DATA["password"]
    assert client.post("/api/v1/auth/login", json=DATA).status_code == 401
    assert client.post("/api/v1/auth/verify", json={"token": token}).status_code == 400
    assert (
        client.post(
            "/api/v1/auth/verify", json={"token": token, "password": "Wrong-password-2026!"}
        ).status_code
        == 400
    )
    assert (
        client.post("/api/v1/auth/verify", json={"token": token, "password": DATA["password"]}).status_code
        == 200
    )
    assert (
        client.post("/api/v1/auth/verify", json={"token": token, "password": DATA["password"]}).status_code
        == 400
    )
    assert client.post("/api/v1/auth/login", json=DATA).status_code == 200


def test_pending_expiry_and_missing_mail_fail_closed(client):
    assert client.post("/api/v1/auth/register", json=DATA).status_code == 503
    token = signup(client)
    with SessionLocal() as db:
        db.get(PendingRegistration, digest(token)).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert (
        client.post("/api/v1/auth/verify", json={"token": token, "password": DATA["password"]}).status_code
        == 400
    )


def test_reset_revokes_sessions_and_token_reuse_and_does_not_enumerate(client):
    user = register(client)
    cfg = settings()
    with patch.object(cfg, "smtp_host", "capture.invalid"):
        known = client.post("/api/v1/auth/recover", json={"email": user["email"]})
        unknown = client.post("/api/v1/auth/recover", json={"email": "absent@example.com"})
    assert known.json() == unknown.json() and known.status_code == unknown.status_code == 200
    token = client.veriora_mail[-1]["token"]
    assert (
        client.post(
            "/api/v1/auth/reset", json={"token": token, "password": "Replacement-password-2026!"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/reset", json={"token": token, "password": "Replacement-password-2026!"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": "safe-test-password-2026"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": user["email"], "password": "Replacement-password-2026!"}
        ).status_code
        == 200
    )


def test_google_state_pkce_single_use_and_no_email_autolinking(client, monkeypatch):
    register(client)
    cfg = settings()
    monkeypatch.setattr(cfg, "google_client_id", "synthetic-client")
    monkeypatch.setattr(cfg, "google_client_secret", "synthetic-secret")
    result = client.post("/api/v1/auth/google/start").json()
    params = parse_qs(urlsplit(result["url"]).query)
    state = params["state"][0]
    assert params["code_challenge_method"] == ["S256"]
    assert client.get("/api/v1/auth/google/callback?state=bad&code=fixture").status_code == 400
    monkeypatch.setattr(
        "app.api.auth.google_claims", lambda *a: {"sub": "synthetic-sub", "email": "reviewer@example.com"}
    )
    result = client.get(
        "/api/v1/auth/google/callback", params={"state": state, "code": "fixture"}, follow_redirects=False
    )
    assert result.status_code == 303 and "link_required" in result.headers["location"]
    assert (
        client.get("/api/v1/auth/google/callback", params={"state": state, "code": "fixture"}).status_code
        == 400
    )
    result = client.post("/api/v1/auth/google/link").json()
    state = parse_qs(urlsplit(result["url"]).query)["state"][0]
    assert (
        client.get(
            "/api/v1/auth/google/callback", params={"state": state, "code": "fixture"}, follow_redirects=False
        ).status_code
        == 303
    )


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"aud": "attacker"},
        {"nonce": "bad"},
        {"iss": "https://attacker.invalid"},
        {"email_verified": False},
        {"exp": 1},
    ],
)
def test_google_jwt_signature_and_claims(monkeypatch, change):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cfg = settings()
    monkeypatch.setattr(cfg, "google_client_id", "client")
    claims = {
        "aud": "client",
        "iss": "https://accounts.google.com",
        "sub": "subject",
        "nonce": "nonce",
        "email": "test@gmail.com",
        "email_verified": True,
        "iat": int(now().timestamp()),
        "exp": int(now().timestamp()) + 60,
        **change,
    }
    encoded = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "fixture"})

    class Keys:
        def get_signing_key_from_jwt(self, token):
            return type("Key", (), {"key": key.public_key()})()

    monkeypatch.setattr(identity, "google_keys", lambda: Keys())
    real = httpx.Client
    monkeypatch.setattr(
        identity.httpx,
        "Client",
        lambda **kw: real(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"id_token": encoded}))
        ),
    )
    if change:
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            identity.google_claims("code", "verifier", "nonce")
    else:
        assert identity.google_claims("code", "verifier", "nonce")["sub"] == "subject"


@pytest.mark.parametrize("language", ["en", "hi", "hinglish"])
def test_multilingual_abstention_never_invents_source(language):
    result = analysis.ask(
        "Kya ye company mera data share karegi?", [], SECTIONS, [], retrieved_chunks=[], language=language
    )
    assert result["answer"] == ABSTENTION[language] and not result["citations"]


def test_summary_uses_verified_quotes_and_not_determinable_when_incomplete():
    section = {
        "id": "sec",
        "source_id": "src",
        "text": "You must pay invoices within thirty days.",
        "page": 2,
    }
    finding = {
        "id": "f",
        "finding_id": "f",
        "category": "OBLIGATION",
        "statement": "Pay in thirty days",
        "support_status": "SUPPORTED",
        "rationale": "Stated term",
        "qualifications": [],
        "citations": [
            {
                "source_id": "src",
                "section_id": "sec",
                "quote": section["text"],
                "start": 0,
                "end": len(section["text"]),
                "page": 2,
            }
        ],
    }
    coverage = {"chunks_total": 1, "chunks_processed": 1, "sections_total": 1, "sections_processed": 1}
    result = summarize([finding], [section], coverage, "COMPLETED")
    assert (
        result["level"] == "Moderate"
        and result["groups"]["obligations"][0]["citations"][0]["quote"] == section["text"]
    )
    assert summarize([finding], [section], coverage, "PARTIAL_COMPLETION")["level"] == "Not Determinable"
    finding["citations"][0]["page"] = 99
    assert summarize([finding], [section], coverage, "COMPLETED")["level"] == "Not Determinable"


def test_language_preference_and_validation(client):
    register(client)
    response = client.patch(
        "/api/v1/me", json={"retention_days": 7, "preferred_provider": "groq", "language": "hi"}
    )
    assert response.status_code == 200 and client.get("/api/v1/me").json()["language"] == "hi"
    assert (
        client.patch(
            "/api/v1/me", json={"retention_days": 7, "preferred_provider": "groq", "language": "unknown"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("language", ["en", "hi", "hinglish"])
def test_grounded_answer_language_directive_preserves_original_quote(monkeypatch, language):
    calls = []

    def generate(providers, system, prompt, schema, role):
        calls.append((system, role))
        if schema is analysis.SourceAnswerDraft:
            return schema(
                answer="The document requires consent.",
                citations=[
                    analysis.SourceCitation(
                        source_id="src1",
                        section_id="sec1",
                        quote=SECTIONS[0]["text"],
                        start=0,
                        end=len(SECTIONS[0]["text"]),
                        page=1,
                    )
                ],
                abstain=False,
                limitations=[],
            ), []
        return analysis.Verdict(
            support_status="SUPPORTED", rationale="Entailed", missing_qualifiers=[], unresolved_references=[]
        ), []

    monkeypatch.setattr(analysis, "generate_with_fallback", generate)
    result = analysis.ask(
        "Kya consent chahiye?", [], SECTIONS, [{}], retrieved_chunks=CHUNKS, language=language
    )
    assert result["citations"][0]["quote"] == SECTIONS[0]["text"]
    from app.services.language import LANGUAGES

    assert LANGUAGES[language] in calls[0][0]


def test_translation_schema_and_separate_fidelity_verification(monkeypatch):
    from app.providers.base import ProviderError
    from app.services import localization

    findings = [
        {
            "id": "f",
            "statement": "Consent is required except when law requires disclosure.",
            "rationale": "Stated exception",
            "qualifications": ["Legal disclosure exception"],
        }
    ]

    def generate(providers, system, prompt, schema, role):
        if schema is localization.Translations:
            return schema(
                findings=[
                    localization.Explanation(
                        finding_id="f",
                        statement="Consent zaroori hai, law ki disclosure exception ke saath.",
                        rationale="Stated exception",
                        qualifications=["Legal disclosure exception"],
                    )
                ]
            ), []
        return analysis.Verdict(
            support_status="SUPPORTED", rationale="Faithful", missing_qualifiers=[], unresolved_references=[]
        ), []

    monkeypatch.setattr(localization, "generate_with_fallback", generate)
    result, _ = localization.localize(findings, "hinglish", [{}])
    assert set(result) == {"f"} and "citation" not in result["f"]

    def reject(*args):
        schema = args[3]
        if schema is localization.Translations:
            return generate(*args)
        return analysis.Verdict(
            support_status="UNSUPPORTED",
            rationale="Negation lost",
            missing_qualifiers=["exception"],
            unresolved_references=[],
        ), []

    monkeypatch.setattr(localization, "generate_with_fallback", reject)
    with pytest.raises(ProviderError, match="TRANSLATION_NOT_VERIFIED"):
        localization.localize(findings, "hi", [{}])


@pytest.mark.parametrize("language", ["hi", "hinglish"])
def test_translation_cache_persistence_ownership_and_quote_integrity(client, monkeypatch, language):
    from conftest import login_guest

    from app.models import Analysis, AnalysisSource, Finding, Job, LocalizedAnalysis, Section, Source
    from app.services import localization

    user = register(client)
    cfg = settings()
    monkeypatch.setattr(cfg, "gemini_api_key", "synthetic")
    monkeypatch.setattr(cfg, "gemini_model", "synthetic")
    text = "Invoices must be paid in thirty days."
    with SessionLocal() as db:
        source = Source(
            owner_id=user["id"],
            original_name="Synthetic.txt",
            kind="text",
            object_key="never-read.enc",
            sha256="a" * 64,
            expires_at=now() + timedelta(days=1),
            status="READY",
        )
        job = Job(owner_id=user["id"], kind="analysis", payload={"provider": "gemini"}, state="COMPLETED")
        db.add_all([source, job])
        db.flush()
        record = Analysis(
            owner_id=user["id"],
            job_id=job.id,
            coverage={"chunks_total": 1, "chunks_processed": 1, "sections_total": 1, "sections_processed": 1},
        )
        db.add(record)
        db.flush()
        db.add(AnalysisSource(analysis_id=record.id, source_id=source.id))
        section = {"id": "sec-cache", "source_id": source.id, "text": text, "page": 1}
        db.add(Section(id=section["id"], source_id=source.id, ordinal=0, data=section))
        f = {
            "id": "finding-cache",
            "finding_id": "finding-cache",
            "category": "OBLIGATION",
            "statement": "Pay within thirty days.",
            "rationale": "Stated term",
            "qualifications": [],
            "support_status": "SUPPORTED",
            "citations": [
                {
                    "source_id": source.id,
                    "section_id": section["id"],
                    "quote": text,
                    "page": 1,
                    "start": 0,
                    "end": len(text),
                }
            ],
        }
        db.add(Finding(id=f["id"], analysis_id=record.id, data=f))
        db.commit()
        ident = record.id
    counter = []

    def translate(*args):
        counter.append(1)
        return {
            "finding-cache": {
                "statement": "Tees din mein payment karein.",
                "rationale": "Stated term",
                "qualifications": [],
            }
        }, []

    monkeypatch.setattr(localization, "localize", translate)
    for _ in range(2):
        assert client.post(f"/api/v1/analyses/{ident}/translations?language={language}").status_code == 200
    assert len(counter) == 1
    result = client.get(f"/api/v1/analyses/{ident}/summary?language={language}").json()
    assert (
        result["translation_ready"]
        and result["summary"]["groups"]["obligations"][0]["citations"][0]["quote"] == text
    )
    # Retained originals and translations remain separate when exporting.
    from app.services import storage

    with SessionLocal() as db:
        original = db.scalar(select(Source).where(Source.owner_id == user["id"]))
        original.object_key, original.sha256 = storage.write(text.encode(), original.id)
        db.commit()
    report = client.get(f"/api/v1/analyses/{ident}/exports?format=json&language={language}")
    assert report.status_code == 200, report.text
    assert report.json()["language"] == language
    assert report.json()["findings"][0]["statement"] == "Tees din mein payment karein."
    assert report.json()["findings"][0]["citations"][0]["quote"] == text
    pdf = client.get(f"/api/v1/analyses/{ident}/exports?format=pdf&language={language}")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    with SessionLocal() as db:
        assert db.scalar(select(LocalizedAnalysis)).language == language
    client.cookies.clear()
    login_guest(client)
    assert client.get(f"/api/v1/analyses/{ident}/summary?language={language}").status_code == 404
    assert client.post(f"/api/v1/analyses/{ident}/translations?language={language}").status_code == 404


def test_smtp_delivery_uses_tls_and_fragment_token(monkeypatch):
    from unittest.mock import MagicMock

    cfg = settings()
    monkeypatch.setattr(cfg, "smtp_host", "mail.example.com")
    monkeypatch.setattr(cfg, "mail_from", "sender@example.com")
    smtp = MagicMock()
    monkeypatch.setattr(identity.smtplib, "SMTP", smtp)
    identity.deliver("recipient@example.com", "verify", "synthetic-token")
    connection = smtp.return_value.__enter__.return_value
    connection.starttls.assert_called_once()
    message = connection.send_message.call_args.args[0]
    assert "#token=synthetic-token" in message.get_content()
    assert "?token=" not in message.get_content()


@pytest.mark.parametrize(
    "text,category,level",
    [
        ("You accept unlimited liability.", "OBLIGATION", "High"),
        ("You do not accept unlimited liability.", "OBLIGATION", "Moderate"),
        ("You have a right to cancel.", "RIGHT", "Low"),
        ("This agreement is effective today.", "CLAUSE", "Not Determinable"),
    ],
)
def test_attention_rules_transparent_high_low_negation(text, category, level):
    section = {"id": "s", "source_id": "doc", "text": text, "page": None}
    finding = {
        "id": "f",
        "category": category,
        "statement": text,
        "rationale": "Source statement",
        "qualifications": [],
        "support_status": "SUPPORTED",
        "citations": [
            {"section_id": "s", "source_id": "doc", "quote": text, "page": None, "start": 0, "end": len(text)}
        ],
    }
    coverage = {"chunks_total": 1, "chunks_processed": 1, "sections_total": 1, "sections_processed": 1}
    assert summarize([finding], [section], coverage, "COMPLETED")["level"] == level
