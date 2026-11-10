"""Isolated auth deployment/security regressions; no production identities or network."""

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.config import Settings, settings
from app.db import SessionLocal
from app.main import app
from app.models import User, now
from app.security import hasher


def test_none_cookie_requires_secure_even_outside_production():
    with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURITY_REQUIRED"):
        Settings(
            _env_file=None,
            database_url="postgresql://fixture:fixture@db.invalid/fixture",
            session_cookie_samesite="none",
            secure_cookies=False,
        )


def test_cross_site_session_login_restore_csrf_logout(client, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "secure_cookies", True)
    monkeypatch.setattr(cfg, "session_cookie_samesite", "none")
    with SessionLocal() as db:
        db.add(
            User(
                email="deployment@example.com",
                password_hash=hasher.hash("Synthetic-password-2026!"),
                verified_at=now(),
            )
        )
        db.commit()
    with TestClient(app, base_url="https://localhost") as browser:
        browser.headers["Origin"] = "http://localhost:5173"
        response = browser.post(
            "/api/v1/auth/login",
            json={"email": "deployment@example.com", "password": "Synthetic-password-2026!"},
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert (
            "SameSite=none" in cookie
            and "Secure" in cookie
            and "HttpOnly" in cookie
            and "Domain=" not in cookie
        )
        assert browser.get("/api/v1/me").status_code == 200
        assert browser.get("/api/v1/dashboard").status_code == 200
        assert browser.get("http://localhost/api/v1/me").status_code == 401
        assert browser.post("/api/v1/auth/logout").status_code == 403
        browser.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        removed = browser.post("/api/v1/auth/logout")
        assert removed.status_code == 204
        assert "SameSite=none" in removed.headers["set-cookie"] and "Secure" in removed.headers["set-cookie"]
        assert browser.get("/api/v1/me").status_code == 401


def test_expected_invalid_credentials_and_unverified_account_are_401(client):
    with SessionLocal() as db:
        db.add(User(email="pending@example.com", password_hash=hasher.hash("Synthetic-password-2026!")))
        db.commit()
    for email in ("missing@example.com", "pending@example.com"):
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "Synthetic-password-2026!"}
        )
        assert response.status_code == 401
        assert response.json()["message"] == "Email or password is incorrect."
    assert client.get("/api/v1/me").status_code == 401
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == "missing@example.com")) is None


def test_browser_callback_error_redirects_without_tokens_and_logs_only_reason(client, caplog):
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        response = client.get(
            "/api/v1/auth/google/callback?code=SECRET_CANARY&state=SECRET_CANARY",
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/sign-in?oauth=failed")
    assert "SECRET_CANARY" not in response.headers["location"]
    assert "OAUTH_BROWSER_STATE_MISSING" in caplog.text and "SECRET_CANARY" not in caplog.text
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/v1/me").status_code == 401
    api = client.get(
        "/api/v1/auth/google/callback?code=fixture&state=fixture", headers={"Accept": "application/json"}
    )
    assert api.status_code == 400 and api.json()["code"] == "OAUTH_BROWSER_STATE_MISSING"
