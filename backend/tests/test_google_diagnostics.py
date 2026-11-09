"""Safe token-stage diagnostics and documented Google issuer compatibility."""

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings
from app.models import now
from app.services import identity


@pytest.mark.parametrize("issuer", ["https://accounts.google.com", "accounts.google.com"])
def test_google_documented_issuers_both_validate(monkeypatch, issuer):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cfg = settings()
    monkeypatch.setattr(cfg, "google_client_id", "synthetic-client")
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": cfg.google_client_id,
            "sub": "fixture",
            "nonce": "nonce",
            "email": "fixture@gmail.com",
            "email_verified": True,
            "iat": int(now().timestamp()),
            "exp": int(now().timestamp()) + 60,
        },
        key,
        algorithm="RS256",
        headers={"kid": "fixture"},
    )
    real = httpx.Client
    monkeypatch.setattr(
        identity.httpx,
        "Client",
        lambda **kw: real(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"id_token": token}))
        ),
    )
    monkeypatch.setattr(
        identity,
        "google_keys",
        lambda: type(
            "Keys",
            (),
            {"get_signing_key_from_jwt": lambda self, token: type("Key", (), {"key": key.public_key()})()},
        )(),
    )
    assert identity.google_claims("code", "verifier", "nonce")["iss"] == issuer


@pytest.mark.parametrize(
    "status,error,expected",
    [
        (400, "invalid_grant", "CODE_REJECTED"),
        (401, "invalid_client", "CLIENT_REJECTED"),
        (400, "unknown", "TOKEN_REJECTED"),
    ],
)
def test_exchange_errors_are_classified_without_returning_provider_body(monkeypatch, status, error, expected):
    real = httpx.Client
    monkeypatch.setattr(
        identity.httpx,
        "Client",
        lambda **kw: real(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    status, json={"error": error, "error_description": "sensitive-fixture-must-not-leak"}
                )
            )
        ),
    )
    with pytest.raises(identity.GoogleVerificationError) as caught:
        identity.google_claims("secret-code", "secret-verifier", "nonce")
    assert caught.value.reason == expected
    assert (
        "sensitive-fixture" not in caught.value.detail
        and "secret-code" not in caught.value.detail
        and "secret-verifier" not in caught.value.detail
    )


@pytest.mark.parametrize(
    "issued_offset,expiry_offset,expected",
    [(15, 60, None), (45, 120, "TOKEN_NOT_YET_VALID"), (0, -1, "TOKEN_EXPIRED"), (0, -60, "TOKEN_EXPIRED")],
)
def test_google_clock_skew_is_bounded_and_expiry_stays_strict(
    monkeypatch, issued_offset, expiry_offset, expected
):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cfg = settings()
    monkeypatch.setattr(cfg, "google_client_id", "synthetic-client")
    stamp = int(now().timestamp())
    token = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": cfg.google_client_id,
            "sub": "clock-fixture",
            "nonce": "nonce",
            "email": "fixture@gmail.com",
            "email_verified": True,
            "iat": stamp + issued_offset,
            "exp": stamp + expiry_offset,
        },
        key,
        algorithm="RS256",
        headers={"kid": "clock-fixture"},
    )
    real = httpx.Client
    monkeypatch.setattr(
        identity.httpx,
        "Client",
        lambda **kw: real(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"id_token": token}))
        ),
    )
    monkeypatch.setattr(
        identity,
        "google_keys",
        lambda: type(
            "Keys",
            (),
            {"get_signing_key_from_jwt": lambda self, token: type("Key", (), {"key": key.public_key()})()},
        )(),
    )
    if expected:
        with pytest.raises(identity.GoogleVerificationError) as caught:
            identity.google_claims("code", "verifier", "nonce")
        assert caught.value.reason == expected
    else:
        assert identity.google_claims("code", "verifier", "nonce")["sub"] == "clock-fixture"
