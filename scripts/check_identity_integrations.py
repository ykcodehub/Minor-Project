"""Explicit integration diagnostics; credentials, addresses and tokens never printed."""

import json
import secrets
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import settings
from app.services.identity import sender_header


def main():
    cfg = settings()
    result = {
        "google_configured": bool(cfg.google_client_id and cfg.google_client_secret),
        "smtp_configured": bool(cfg.smtp_host and cfg.mail_from),
    }
    if result["smtp_configured"]:
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
                result["smtp_authenticated"] = smtp.noop()[0] == 250
                if "--send-self-test" in sys.argv:
                    sender = sender_header()
                    address = parseaddr(sender)[1]
                    if not address or "@" not in address:
                        raise ValueError("Invalid sender")
                    message = EmailMessage()
                    message["From"] = sender
                    message["To"] = address
                    message["Subject"] = "Veriora SMTP delivery check"
                    message.set_content(
                        "This is a Veriora SMTP integration check sent to the configured sender address. No action is required. It contains no credentials, verification codes or document content."
                    )
                    result["smtp_message_accepted"] = not smtp.send_message(message)
        except (OSError, smtplib.SMTPException, ValueError, HTTPException) as exc:
            result["smtp_error"] = type(exc).__name__
    if result["google_configured"]:
        try:
            url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
                {
                    "client_id": cfg.google_client_id,
                    "redirect_uri": cfg.google_redirect_uri,
                    "response_type": "code",
                    "scope": "openid email",
                    "state": secrets.token_urlsafe(32),
                    "nonce": secrets.token_urlsafe(32),
                }
            )
            with httpx.Client(timeout=20, follow_redirects=True) as client:
                response = client.get(url)
            result["google_authorization_http_status"] = response.status_code
            result["google_authorization_page_reached"] = (
                response.status_code == 200
                and not any(
                    marker in response.text.lower()
                    for marker in (
                        "redirect_uri_mismatch",
                        "error 401: invalid_client",
                        "error 400: invalid_request",
                    )
                )
            )
            result["google_callback_verified"] = False
        except httpx.HTTPError as exc:
            result["google_error"] = type(exc).__name__
    (ROOT / "docs/verification-artifacts/identity-integrations.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
