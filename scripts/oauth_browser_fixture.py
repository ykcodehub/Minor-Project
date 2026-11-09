"""Isolated browser-only Google boundary fixture, never a production identity bypass.

JWT signature/issuer/audience/nonce checks still execute in the real verifier.
Only Google's remote token/JWKS boundary uses synthetic keys/claims.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import settings

cfg = settings()
if not (
    cfg.environment == "test"
    and os.environ.get("VERIORA_TEST_ISOLATED") == "1"
    and cfg.database_url.startswith("sqlite:///")
    and "e2e-" in str(cfg.storage_path)
):
    raise RuntimeError("OAuth browser fixture requires isolated test database/storage")
cfg.google_client_id = "synthetic-browser-client"
cfg.google_client_secret = "synthetic-browser-secret"
cfg.google_redirect_uri = "http://localhost:5174/api/v1/auth/google/callback"
cfg.public_url = "http://localhost:5174"

from app.models import now
from app.services import identity

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token_response(request):
    from urllib.parse import parse_qs

    form = parse_qs(request.content.decode())
    code = form.get("code", [""])[0]
    if not code.startswith("browser-fixture-"):
        return httpx.Response(400, json={"error": "invalid_grant"})
    nonce = code.removeprefix("browser-fixture-")
    claims = {
        "iss": "https://accounts.google.com",
        "aud": cfg.google_client_id,
        "sub": "synthetic-browser-subject",
        "email": "synthetic-browser-google@gmail.com",
        "email_verified": True,
        "nonce": nonce,
        "iat": int(now().timestamp()),
        "exp": int(now().timestamp()) + 60,
    }
    token = jwt.encode(
        claims, key, algorithm="RS256", headers={"kid": "synthetic-browser-key"}
    )
    return httpx.Response(200, json={"id_token": token})


class Keys:
    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=key.public_key())


real_client = httpx.Client
identity.httpx = SimpleNamespace(
    Client=lambda **kw: real_client(
        transport=httpx.MockTransport(token_response), **kw
    ),
    HTTPError=httpx.HTTPError,
)
identity.google_keys = lambda: Keys()
from app.main import app  # noqa: F401
