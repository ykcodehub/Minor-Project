"""OAuth host/cookie/state regression tests. No real Google identity or secrets."""

import json
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import OAuthAttempt, User, now
from app.security import digest


@pytest.fixture
def google(client, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "google_client_id", "synthetic-client")
    monkeypatch.setattr(cfg, "google_client_secret", "synthetic-secret")
    monkeypatch.setattr(cfg, "google_redirect_uri", "http://localhost:5173/api/v1/auth/google/callback")
    monkeypatch.setattr(cfg, "public_url", "http://localhost:5173")
    monkeypatch.setattr(cfg, "secure_cookies", False)
    return client


def start(client):
    response = client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert response.status_code == 303
    params = parse_qs(urlsplit(response.headers["location"]).query)
    return response, params


def test_navigation_sets_cookie_before_google_and_uses_exact_redirect(google):
    response, params = start(google)
    assert params["redirect_uri"] == [settings().google_redirect_uri]
    assert params["code_challenge_method"] == ["S256"]
    assert params["nonce"] and params["state"]
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=600" in cookie
    assert "Path=/api/v1/auth/google" in cookie and "Domain=" not in cookie
    with SessionLocal() as db:
        attempt = db.get(OAuthAttempt, digest(params["state"][0]))
        assert attempt and attempt.nonce_hash == digest(params["nonce"][0])


def test_alias_is_canonicalized_without_creating_wrong_host_cookie(google):
    response = google.get("http://127.0.0.1:5173/api/v1/auth/google/login", follow_redirects=False)
    assert (
        response.status_code == 303
        and response.headers["location"] == "http://localhost:5173/api/v1/auth/google/login"
    )
    assert "set-cookie" not in response.headers
    response = google.post(
        "http://127.0.0.1:5173/api/v1/auth/google/start", headers={"Origin": "http://127.0.0.1:5173"}
    )
    assert (
        response.status_code == 200
        and response.json()["url"] == "http://localhost:5173/api/v1/auth/google/login"
    )
    assert "set-cookie" not in response.headers
    with SessionLocal() as db:
        assert not db.scalar(select(OAuthAttempt))


def test_success_persists_across_app_clients_and_consumes_state(google, monkeypatch):
    _, params = start(google)
    state = params["state"][0]
    calls = []

    def claims(code, verifier, nonce):
        calls.append(code)
        assert nonce == params["nonce"][0] and len(verifier) >= 32
        return {"sub": "fixture-google-sub", "email": "oauth-fixture@gmail.com"}

    monkeypatch.setattr("app.api.auth.google_claims", claims)
    # A separate API client/application session uses only durable DB state and the browser cookie.
    with TestClient(app, base_url="http://localhost") as second:
        second.cookies.update(google.cookies)
        response = second.get(
            "/api/v1/auth/google/callback",
            params={"code": "fixture-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 303 and response.headers["location"].endswith("/dashboard")
        assert second.get("/api/v1/me").json()["verified"]
        assert second.get("/api/v1/dashboard").status_code == 200
        replay = second.get("/api/v1/auth/google/callback", params={"code": "fixture-code", "state": state})
        assert replay.status_code == 400
    assert calls == ["fixture-code"]
    with SessionLocal() as db:
        assert db.get(OAuthAttempt, digest(state)) is None


@pytest.mark.parametrize(
    "case",
    [
        "missing_cookie",
        "wrong_state",
        "missing_state",
        "missing_code",
        "expired",
        "wrong_nonce",
        "malformed_cookie",
    ],
)
def test_invalid_callbacks_never_exchange_code_or_create_session(google, monkeypatch, case):
    _, params = start(google)
    state = params["state"][0]
    query = {"state": state, "code": "fixture-code"}

    def forbidden(*args):
        raise AssertionError("Provider must not receive an invalid callback")

    monkeypatch.setattr("app.api.auth.google_claims", forbidden)
    if case == "missing_cookie":
        google.cookies.clear()
    elif case == "wrong_state":
        query["state"] = "mismatching-state"
    elif case == "missing_state":
        query.pop("state")
    elif case == "missing_code":
        query.pop("code")
    elif case == "expired":
        with SessionLocal() as db:
            db.get(OAuthAttempt, digest(state)).expires_at = now() - timedelta(seconds=1)
            db.commit()
    else:
        google.cookies.clear()
        value = (
            json.dumps([state, "wrong-nonce-" + "x" * 32, "v" * 43])
            if case == "wrong_nonce"
            else json.dumps([state, 123, {}])
        )
        google.cookies.set("veriora_oauth", value, domain="localhost.local", path="/api/v1/auth/google")
    assert google.get("/api/v1/auth/google/callback", params=query, follow_redirects=False).status_code == 400
    assert google.get("/api/v1/me").status_code == 401
    with SessionLocal() as db:
        assert not db.scalar(select(User))


def test_cancellation_consumes_matching_state_without_provider_call(google, monkeypatch):
    _, params = start(google)
    state = params["state"][0]
    monkeypatch.setattr(
        "app.api.auth.google_claims", lambda *a: pytest.fail("No token exchange on cancellation")
    )
    response = google.get("/api/v1/auth/google/callback", params={"state": state, "error": "access_denied"})
    assert response.status_code == 400
    with SessionLocal() as db:
        assert db.get(OAuthAttempt, digest(state)) is None


def test_identity_failure_reports_safe_code_and_consumes_attempt(google, monkeypatch):
    from app.models import AuditEvent
    from app.services.identity import GoogleVerificationError

    _, params = start(google)
    state = params["state"][0]

    def reject(*args):
        raise GoogleVerificationError("NONCE_INVALID", "The identity did not match this browser.")

    monkeypatch.setattr("app.api.auth.google_claims", reject)
    result = google.get(
        "/api/v1/auth/google/callback", params={"code": "secret-fixture-code", "state": state}
    )
    assert result.status_code == 400 and result.json()["code"] == "GOOGLE_NONCE_INVALID"
    assert "secret-fixture-code" not in result.text and state not in result.text
    with SessionLocal() as db:
        assert db.get(OAuthAttempt, digest(state)) is None
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "oauth.failed.nonce_invalid"))
        assert audit.object_id == result.json()["request_id"]


def test_production_proxy_host_is_explicit_not_forwarded_header_trust(google, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "environment", "production")
    monkeypatch.setattr(cfg, "google_redirect_uri", "https://app.example.com/api/v1/auth/google/callback")
    monkeypatch.setattr(cfg, "oauth_proxy_hosts", "api.example.com")
    response = google.get("https://api.example.com/api/v1/auth/google/login", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].startswith(
        "https://accounts.google.com/"
    )
    response = google.get(
        "https://untrusted.example.com/api/v1/auth/google/login",
        headers={"X-Forwarded-Host": "app.example.com"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "https://app.example.com/api/v1/auth/google/login"


def test_http_production_ingress_fails_closed_instead_of_redirect_loop(google, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "environment", "production")
    monkeypatch.setattr(cfg, "google_redirect_uri", "https://app.example.com/api/v1/auth/google/callback")
    monkeypatch.setattr(cfg, "oauth_proxy_hosts", "api.example.com")
    response = google.get("http://api.example.com/api/v1/auth/google/login", follow_redirects=False)
    assert response.status_code == 503
    assert response.json()["code"] == "OAUTH_HTTPS_PROXY_REQUIRED"
    assert "location" not in response.headers and "set-cookie" not in response.headers
    with SessionLocal() as db:
        assert not db.scalar(select(OAuthAttempt))
