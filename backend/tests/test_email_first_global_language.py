"""Email ownership precedes password setup; global language never alters source data."""

from datetime import timedelta
from unittest.mock import patch

from conftest import login_guest
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import PendingRegistration, User, now
from app.security import digest

EMAIL = "new-flow@example.com"
PASSWORD = "Confirmed-password-2026!"


def start(client, email=EMAIL):
    cfg = settings()
    with (
        patch.object(cfg, "smtp_host", "synthetic.invalid"),
        patch.object(cfg, "mail_from", "sender@example.com"),
    ):
        response = client.post("/api/v1/auth/registration/start", json={"email": email})
    assert response.status_code == 202, response.text
    return response


def test_email_only_then_verification_then_confirmed_password(client):
    start(client)
    token = client.veriora_mail[-1]["token"]
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == EMAIL)) is None
        assert db.get(PendingRegistration, digest(token)).password_hash == ""
    assert (
        client.post(
            "/api/v1/auth/registration/complete",
            json={"token": token, "password": PASSWORD, "confirm_password": PASSWORD},
        ).status_code
        == 400
    )
    verified = client.post("/api/v1/auth/registration/verify", json={"token": token})
    assert verified.status_code == 200
    setup = verified.json()["setup_token"]
    assert setup != token
    assert client.post("/api/v1/auth/registration/verify", json={"token": token}).status_code == 400
    with SessionLocal() as db:
        assert db.get(PendingRegistration, digest(token)) is None
        assert db.get(PendingRegistration, digest(setup)).verified_at
        assert db.scalar(select(User).where(User.email == EMAIL)) is None
    assert (
        client.post(
            "/api/v1/auth/registration/complete",
            json={"token": setup, "password": PASSWORD, "confirm_password": "Mismatch-password-2026!"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/registration/complete",
            json={"token": setup, "password": PASSWORD, "confirm_password": PASSWORD},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/auth/registration/complete",
            json={"token": setup, "password": PASSWORD, "confirm_password": PASSWORD},
        ).status_code
        == 400
    )
    assert client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200


def test_expired_setup_and_email_are_not_accounts(client):
    start(client)
    token = client.veriora_mail[-1]["token"]
    setup = client.post("/api/v1/auth/registration/verify", json={"token": token}).json()["setup_token"]
    with SessionLocal() as db:
        db.get(PendingRegistration, digest(setup)).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert (
        client.post(
            "/api/v1/auth/registration/complete",
            json={"token": setup, "password": PASSWORD, "confirm_password": PASSWORD},
        ).status_code
        == 400
    )
    assert client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401


def test_global_guest_language_is_persisted_scoped_and_csrf_protected(client):
    user = login_guest(client)
    for language in ("hi", "hinglish", "en"):
        response = client.patch("/api/v1/me/language", json={"language": language})
        assert response.status_code == 200 and response.json()["language"] == language
        with SessionLocal() as db:
            assert db.get(User, user["id"]).language == language
    assert client.patch("/api/v1/me/language", json={"language": "de"}).status_code == 422
    assert (
        client.patch(
            "/api/v1/me/language", json={"language": "hi"}, headers={"X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
