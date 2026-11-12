"""Email delivery and Google OIDC, with no credential/token logging."""

import secrets
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from functools import lru_cache

import httpx
import jwt
from fastapi import HTTPException

from app.config import settings


def sender_header():
    from email.utils import formataddr, parseaddr

    from pydantic import EmailStr, TypeAdapter, ValidationError

    cfg = settings()
    if "\r" in cfg.mail_from or "\n" in cfg.mail_from:
        raise HTTPException(503, "Email sender configuration is invalid.")
    name, address = parseaddr(cfg.mail_from)
    try:
        address = str(TypeAdapter(EmailStr).validate_python(address))
    except ValidationError:
        try:
            address = str(TypeAdapter(EmailStr).validate_python(cfg.smtp_user))
            name = cfg.mail_from
        except ValidationError:
            raise HTTPException(503, "Email sender configuration needs a valid mailbox address.") from None
    return formataddr((name, address)) if name else address


def deliver(email, purpose, token):
    cfg = settings()
    if cfg.environment == "test" and cfg.test_mail_outbox:
        import json

        cfg.test_mail_outbox.parent.mkdir(parents=True, exist_ok=True)
        with cfg.test_mail_outbox.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"email": email, "purpose": purpose, "token": token}) + "\n")
        return
    if not cfg.smtp_host or not cfg.mail_from:
        raise HTTPException(503, "Email delivery is not configured. Contact the administrator.")
    message = EmailMessage()
    message["From"], message["To"] = sender_header(), email
    message["Subject"] = (
        "Verify your Veriora email" if purpose in {"verify", "signup"} else "Reset your Veriora password"
    )
    # Fragments are not sent in HTTP requests/access logs or Referer headers.
    message.set_content(
        f"Open {cfg.public_url}/sign-in?purpose={purpose}#token={token}\n"
        + (
            "This single-use link expires in one hour. After verification, you will create a new password.\n"
            if purpose == "signup"
            else "This single-use link expires in one hour. Use it to create a new password.\n"
        )
        + "If you did not request this, ignore this message."
    )
    try:
        if cfg.smtp_use_ssl or cfg.smtp_port == 465:
            smtp = smtplib.SMTP_SSL(
                cfg.smtp_host,
                cfg.smtp_port,
                timeout=15,
                context=ssl.create_default_context(),
            )
        else:
            smtp = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15)
        with smtp:
            if cfg.smtp_port != 465 and not cfg.smtp_use_ssl:
                smtp.starttls(context=ssl.create_default_context())
            if cfg.smtp_user:
                smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise HTTPException(503, "Email could not be delivered. Please retry later.") from None


@lru_cache
def google_keys():
    return jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", timeout=10)


GOOGLE_CLOCK_SKEW_SECONDS = 30


class GoogleVerificationError(HTTPException):
    def __init__(self, reason, message, status_code=400):
        self.reason = reason
        self.public_code = "GOOGLE_" + reason
        super().__init__(status_code, message)


def google_claims(code, verifier, nonce):
    cfg = settings()
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "code_verifier": verifier,
                    "client_id": cfg.google_client_id,
                    "client_secret": cfg.google_client_secret,
                    "redirect_uri": cfg.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
    except httpx.HTTPError:
        raise GoogleVerificationError(
            "TOKEN_NETWORK", "Google's token service could not be reached. Start sign-in again shortly.", 503
        ) from None
    if response.status_code != 200:
        try:
            error = response.json().get("error")
        except (ValueError, AttributeError):
            error = None
        if error == "invalid_client" or response.status_code == 401:
            raise GoogleVerificationError(
                "CLIENT_REJECTED",
                "Google rejected the OAuth client configuration. Check the configured Web client and secret.",
            )
        if error == "invalid_grant":
            raise GoogleVerificationError(
                "CODE_REJECTED",
                "Google rejected or expired the authorization code. Start a fresh Google sign-in; do not reload the callback.",
            )
        raise GoogleVerificationError(
            "TOKEN_REJECTED", "Google could not complete the token exchange. Start a fresh Google sign-in."
        )
    try:
        token = response.json()["id_token"]
        if not isinstance(token, str):
            raise TypeError()
    except (ValueError, KeyError, TypeError):
        raise GoogleVerificationError(
            "TOKEN_MALFORMED", "Google did not return a valid identity token."
        ) from None
    try:
        key = google_keys().get_signing_key_from_jwt(token)
    except jwt.PyJWTError:
        raise GoogleVerificationError(
            "SIGNING_KEY_UNAVAILABLE",
            "Google's signing key could not be retrieved or matched. Retry a fresh sign-in shortly.",
            503,
        ) from None
    try:
        # Google documents both spellings as valid issuers; no other issuer is trusted.
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=cfg.google_client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
            leeway=GOOGLE_CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce", "email", "email_verified"]},
        )
    except jwt.ExpiredSignatureError:
        raise GoogleVerificationError(
            "TOKEN_EXPIRED",
            "The Google identity token expired. Check the server clock and start sign-in again.",
        ) from None
    except jwt.ImmatureSignatureError:
        raise GoogleVerificationError(
            "TOKEN_NOT_YET_VALID", "The Google identity token is not valid yet. Check the server clock."
        ) from None
    except jwt.InvalidAudienceError:
        raise GoogleVerificationError(
            "AUDIENCE_INVALID", "The Google identity token belongs to a different OAuth client."
        ) from None
    except jwt.InvalidIssuerError:
        raise GoogleVerificationError(
            "ISSUER_INVALID", "The identity token was not issued by a trusted Google issuer."
        ) from None
    except jwt.InvalidSignatureError:
        raise GoogleVerificationError(
            "SIGNATURE_INVALID", "The Google identity token signature could not be verified."
        ) from None
    except (jwt.PyJWTError, ValueError, TypeError):
        raise GoogleVerificationError(
            "TOKEN_INVALID", "The Google identity token did not pass required claim validation."
        ) from None
    # Allow only a bounded issuer-clock lead; do not extend token expiration.
    if int(claims["exp"]) <= datetime.now(UTC).timestamp():
        raise GoogleVerificationError(
            "TOKEN_EXPIRED", "The Google identity token expired. Start sign-in again."
        )
    if not isinstance(claims.get("nonce"), str) or not secrets.compare_digest(claims["nonce"], nonce):
        raise GoogleVerificationError(
            "NONCE_INVALID", "The Google identity token does not match this browser sign-in attempt."
        )
    if claims.get("email_verified") is not True:
        raise GoogleVerificationError(
            "EMAIL_UNVERIFIED",
            "Google has not verified this email. Verify it with Google or use email registration.",
        )
    if (
        claims.get("azp", cfg.google_client_id) != cfg.google_client_id
        or not isinstance(claims.get("sub"), str)
        or not 1 <= len(claims["sub"]) <= 255
    ):
        raise GoogleVerificationError(
            "IDENTITY_INVALID", "The Google identity does not match the authorized client or account."
        )
    from pydantic import EmailStr, TypeAdapter, ValidationError

    try:
        claims["email"] = str(TypeAdapter(EmailStr).validate_python(claims["email"])).lower()
    except (ValidationError, TypeError, KeyError):
        raise GoogleVerificationError(
            "EMAIL_INVALID", "Google did not provide a valid email address."
        ) from None
    if not claims["email"].endswith("@gmail.com") and not claims.get("hd"):
        raise GoogleVerificationError(
            "EMAIL_OWNERSHIP_REQUIRED",
            "This Google account uses a third-party email address. Verify email ownership through email registration, then link Google from Account settings.",
        )
    return claims
