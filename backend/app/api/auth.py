import base64
import hashlib
import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select

from app.config import settings
from app.models import AuthToken, OAuthAttempt, OAuthIdentity, PendingRegistration, Session, Source, User, now
from app.schemas import (
    AccountInput,
    Credentials,
    EmailRequest,
    LanguageInput,
    ProfileResponse,
    RegistrationComplete,
    TokenRequest,
)
from app.security import (
    DUMMY_PASSWORD_HASH,
    CurrentUser,
    Db,
    clear_session,
    create_session,
    digest,
    hasher,
    password_valid,
    throttle,
)
from app.services.identity import GoogleVerificationError, deliver, google_claims
from app.services.resources import audit, delete_source, flush_storage_deletions, source_dict

router = APIRouter()


def profile(user, csrf):
    return {
        "id": user.id,
        "email": user.email,
        "is_guest": user.is_guest,
        "csrf_token": csrf,
        "retention_days": user.retention_days,
        "preferred_provider": user.preferred_provider,
        "verified": user.verified_at is not None,
        "language": user.language,
        "providers": [
            {"name": p["name"], "model": p["model"], "configured": bool(p["key"] and p["model"])}
            for p in settings().providers()
        ],
    }


def send_token(db, user, purpose):
    token = secrets.token_urlsafe(32)
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id, AuthToken.purpose == purpose))
    db.add(
        AuthToken(id=digest(token), user_id=user.id, purpose=purpose, expires_at=now() + timedelta(hours=1))
    )
    deliver(user.email, purpose, token)


@router.get("/me", response_model=ProfileResponse)
def me(request: Request, user: CurrentUser):
    return profile(user, request.state.session.csrf)


@router.post("/auth/guest", status_code=201, response_model=ProfileResponse)
def guest(request: Request, response: Response, db: Db):
    cookie = request.cookies.get("veriora_session")
    existing = db.get(Session, digest(cookie)) if cookie else None
    if existing and existing.expires_at.replace(tzinfo=now().tzinfo) > now():
        current = db.get(User, existing.user_id)
        if current:
            return profile(current, existing.csrf)
    throttle(db, "guest:" + (request.client.host if request.client else "unknown"), 5, 3600)
    user = User(is_guest=True, retention_days=1)
    db.add(user)
    db.flush()
    record = create_session(db, user, response)
    db.commit()
    return profile(user, record.csrf)


@router.post("/auth/register", status_code=202)
def register(data: Credentials, request: Request, db: Db):
    throttle(db, "register-ip:" + (request.client.host if request.client else "unknown"), 5, 3600)
    email = str(data.email).lower()
    throttle(db, "register-email:" + email, 3, 3600)
    if not settings().smtp_host or not settings().mail_from:
        raise HTTPException(503, "Email delivery is not configured. Registration is unavailable.")
    encoded = hasher.hash(data.password)
    message = {"message": "If this address can be registered, a verification link will be sent."}
    if db.scalar(select(User).where(User.email == email)):
        return message
    # Never replace an outstanding signup's password: only its mailbox holder can complete it.
    pending = db.scalar(
        select(PendingRegistration).where(PendingRegistration.email == email).with_for_update()
    )
    if pending and pending.expires_at.replace(tzinfo=now().tzinfo) > now():
        return message
    if pending:
        db.delete(pending)
        db.flush()
    cookie = request.cookies.get("veriora_session", "")
    session = db.get(Session, digest(cookie)) if cookie else None
    guest = db.get(User, session.user_id) if session else None
    guest_valid = guest and guest.is_guest and session.expires_at.replace(tzinfo=now().tzinfo) > now()
    if guest_valid and not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.csrf):
        raise HTTPException(403, "Reload your session and retry.")
    token = secrets.token_urlsafe(32)
    db.add(
        PendingRegistration(
            id=digest(token),
            email=email,
            password_hash=encoded,
            expires_at=now() + timedelta(hours=1),
            guest_id=guest.id if guest_valid else None,
            session_hash=session.id if guest_valid else None,
        )
    )
    try:
        deliver(email, "verify", token)
    except HTTPException:
        db.rollback()
        return message
    db.commit()
    return message


@router.post("/auth/login", response_model=ProfileResponse)
def login(data: Credentials, request: Request, response: Response, db: Db):
    throttle(db, "login-ip:" + (request.client.host if request.client else "unknown"), 20, 900)
    throttle(db, "login-email:" + str(data.email).lower(), 10, 900)
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    # Hash unknown passwords too, avoiding a fast account-enumeration path.
    encoded = user.password_hash if user and user.password_hash else DUMMY_PASSWORD_HASH
    if not password_valid(encoded, data.password) or not user or not user.verified_at:
        raise HTTPException(401, "Email or password is incorrect.")
    prior = request.cookies.get("veriora_session")
    if prior:
        db.execute(delete(Session).where(Session.id == digest(prior)))
    record = create_session(db, user, response)
    db.commit()
    return profile(user, record.csrf)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Db, user: CurrentUser):
    db.delete(request.state.session)
    db.commit()
    clear_session(response)


@router.post("/auth/recover")
def recover(data: EmailRequest, request: Request, db: Db):
    throttle(db, "recover:" + (request.client.host if request.client else "unknown"), 5, 900)
    if not settings().smtp_host:
        raise HTTPException(503, "Email recovery is not configured. Contact the deployment administrator.")
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if user and user.password_hash and user.verified_at:
        try:
            send_token(db, user, "recover")
            db.commit()
        except HTTPException:
            db.rollback()  # Same response for unavailable delivery and unknown addresses.

    return {"message": "If an account exists, recovery instructions will be sent."}


@router.post("/auth/verify")
def verify_email(data: TokenRequest, request: Request, response: Response, db: Db):
    throttle(db, "verify:" + (request.client.host if request.client else "unknown"), 10, 900)
    pending = db.scalar(
        select(PendingRegistration).where(PendingRegistration.id == digest(data.token)).with_for_update()
    )
    if pending:
        if (
            pending.expires_at.replace(tzinfo=now().tzinfo) <= now()
            or not data.password
            or not password_valid(pending.password_hash, data.password)
        ):
            raise HTTPException(400, "Verification link or password is invalid or expired.")
        if db.scalar(select(User).where(User.email == pending.email)):
            raise HTTPException(400, "Verification link is no longer valid. Sign in instead.")
        cookie = request.cookies.get("veriora_session", "")
        prior = db.get(Session, digest(cookie)) if cookie else None
        guest = db.get(User, pending.guest_id) if pending.guest_id else None
        if (
            guest
            and guest.is_guest
            and prior
            and prior.id == pending.session_hash
            and prior.user_id == guest.id
            and prior.expires_at.replace(tzinfo=now().tzinfo) > now()
        ):
            if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), prior.csrf):
                raise HTTPException(403, "Reload your session and retry.")
            user = guest
            user.email, user.password_hash, user.is_guest = pending.email, pending.password_hash, False
            user.retention_days = 30
            for source in db.scalars(
                select(Source).where(Source.owner_id == user.id, Source.expires_at > now())
            ):
                source.expires_at = source.captured_at.replace(tzinfo=now().tzinfo) + timedelta(days=30)
            db.execute(delete(Session).where(Session.user_id == user.id))
        else:
            user = User(email=pending.email, password_hash=pending.password_hash)
            db.add(user)
        user.verified_at = now()
        db.flush()
        db.delete(pending)
        audit(db, user.id, "account.email_verified", user.id)
        db.commit()
        return {"message": "Email verified. Sign in to continue."}
    # Preserve older issued verification links; no new unverified users are created.
    token = db.scalar(select(AuthToken).where(AuthToken.id == digest(data.token)).with_for_update())
    if not token or token.purpose != "verify" or token.expires_at.replace(tzinfo=now().tzinfo) <= now():
        raise HTTPException(400, "Verification link is invalid or expired.")
    db.get(User, token.user_id).verified_at = now()
    db.delete(token)
    db.commit()
    return {"message": "Email verified. Sign in to continue."}


@router.post("/auth/reset")
def reset_password(data: TokenRequest, request: Request, db: Db):
    throttle(db, "reset:" + (request.client.host if request.client else "unknown"), 10, 900)
    token = db.scalar(select(AuthToken).where(AuthToken.id == digest(data.token)).with_for_update())
    if (
        not data.password
        or not token
        or token.purpose != "recover"
        or token.expires_at.replace(tzinfo=now().tzinfo) <= now()
    ):
        raise HTTPException(400, "Recovery link is invalid or expired.")
    db.get(User, token.user_id).password_hash = hasher.hash(data.password)
    db.execute(delete(Session).where(Session.user_id == token.user_id))
    db.delete(token)
    db.commit()
    return {"message": "Password updated. Sign in again."}


@router.patch("/me")
def update_account(data: AccountInput, request: Request, db: Db, user: CurrentUser):
    if user.is_guest:
        raise HTTPException(403, "Create an account to save settings.")
    user.retention_days = data.retention_days
    user.preferred_provider = data.preferred_provider
    if data.language is not None:
        user.language = data.language
    # Shortening retention applies immediately to retained sources.
    for source in db.scalars(select(Source).where(Source.owner_id == user.id)):
        new_expiry = source.captured_at.replace(tzinfo=now().tzinfo) + timedelta(days=data.retention_days)
        if new_expiry < source.expires_at.replace(tzinfo=now().tzinfo):
            source.expires_at = new_expiry
    db.commit()
    return profile(user, request.state.session.csrf)


@router.get("/me/export")
def export_account(db: Db, user: CurrentUser):
    if user.is_guest:
        raise HTTPException(403, "Create an account to export retained data.")
    sources = db.scalars(select(Source).where(Source.owner_id == user.id, Source.expires_at > now())).all()
    return {
        "account": {"id": user.id, "email": user.email, "retention_days": user.retention_days},
        "sources": [source_dict(s) for s in sources],
        "notice": "Download individual source originals and analysis manifests from your library.",
    }


@router.delete("/me", status_code=204)
def delete_account(response: Response, db: Db, user: CurrentUser):
    for source in db.scalars(select(Source).where(Source.owner_id == user.id)).all():
        delete_source(db, source)
    audit(db, user.id, "account.deleted", user.id)
    db.delete(user)
    db.commit()
    flush_storage_deletions(db)
    clear_session(response)


@router.get("/auth/options")
def auth_options():
    cfg = settings()
    return {
        "google": bool(cfg.google_client_id and cfg.google_client_secret),
        "google_login_url": google_login_url(),
        "email": bool(cfg.smtp_host and cfg.mail_from),
    }


OAUTH_COOKIE_PATH = "/api/v1/auth/google"


def clear_google_cookie(response):
    response.delete_cookie(
        "veriora_oauth",
        path=OAUTH_COOKIE_PATH,
        httponly=True,
        secure=settings().secure_cookies,
        samesite="lax",
    )


def google_state_error(code, message):
    failure = HTTPException(400, message)
    failure.public_code = code
    return failure


def google_login_url():
    target = urlsplit(settings().google_redirect_uri)
    return f"{target.scheme}://{target.netloc}{OAUTH_COOKIE_PATH}/login"


def google_cookie_origin_matches(request):
    target = urlsplit(settings().google_redirect_uri)
    direct = request.url.hostname == target.hostname and request.url.scheme == target.scheme
    # Explicit ingress host allowlist supports same-origin external rewrites without trusting
    # arbitrary X-Forwarded-Host input. The UI always enters at the configured public origin.
    cfg = settings()
    proxy = (
        cfg.environment == "production"
        and request.url.hostname in {h.strip() for h in cfg.oauth_proxy_hosts.split(",") if h.strip()}
        and request.url.scheme == "https"
        and target.scheme == "https"
    )
    return direct or proxy


def begin_google(db, request, link_user=None, navigation=False):
    cfg = settings()
    if not cfg.google_client_id or not cfg.google_client_secret:
        raise HTTPException(503, "Google sign-in is not configured.")
    if not google_cookie_origin_matches(request):
        if link_user:
            raise HTTPException(
                409, "Open the configured application URL and sign in there before linking Google."
            )
        # A trusted ingress reporting HTTP for an HTTPS callback would redirect to itself
        # forever. Fail closed; only the hosting proxy's trusted forwarding setup can fix it.
        target = urlsplit(cfg.google_redirect_uri)
        ingress = {target.hostname, *[h.strip() for h in cfg.oauth_proxy_hosts.split(",") if h.strip()]}
        if (
            cfg.environment == "production"
            and request.url.hostname in ingress
            and request.url.scheme != target.scheme
        ):
            failure = HTTPException(
                503,
                "OAuth HTTPS proxy configuration is invalid. Configure trusted forwarding headers and HTTPS.",
            )
            failure.public_code = "OAUTH_HTTPS_PROXY_REQUIRED"
            raise failure
        # Never set a cookie on an alias that cannot receive the configured callback.
        if navigation:
            return RedirectResponse(google_login_url(), status_code=303)
        return {"url": google_login_url()}
    throttle(db, "google:" + (request.client.host if request.client else "unknown"), 10, 900)
    state, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(3)]
    db.add(
        OAuthAttempt(
            id=digest(state),
            nonce_hash=digest(nonce),
            verifier_hash=digest(verifier),
            expires_at=now() + timedelta(minutes=10),
            link_user_id=link_user,
        )
    )
    db.commit()
    authorization_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": cfg.google_client_id,
            "redirect_uri": cfg.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email",
            "state": state,
            "nonce": nonce,
            "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode(),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    response = (
        RedirectResponse(authorization_url, status_code=303)
        if navigation
        else Response(content=json.dumps({"url": authorization_url}), media_type="application/json")
    )
    response.set_cookie(
        "veriora_oauth",
        json.dumps([state, nonce, verifier]),
        max_age=600,
        httponly=True,
        secure=cfg.secure_cookies,
        samesite="lax",
        path=OAUTH_COOKIE_PATH,
    )
    return response


@router.get("/auth/google/login")
def google_login(request: Request, db: Db):
    """Top-level navigation on the callback origin establishes the browser cookie first."""
    return begin_google(db, request, navigation=True)


@router.post("/auth/google/start")
def google_start(request: Request, db: Db):
    return begin_google(db, request)


@router.post("/auth/google/link")
def google_link(request: Request, db: Db, user: CurrentUser):
    if user.is_guest or not user.verified_at:
        raise HTTPException(403, "Sign in to your verified account before linking Google.")
    return begin_google(db, request, user.id)


@router.get("/auth/google/callback")
def google_callback(request: Request, db: Db, state: str = "", code: str = "", error: str = ""):
    try:
        stored_state, nonce, verifier = json.loads(request.cookies.get("veriora_oauth", ""))
        if (
            not state
            or len(state) > 100
            or (not code and not error)
            or len(code) > 4096
            or not all(
                isinstance(value, str) and 32 <= len(value) <= 100
                for value in (stored_state, nonce, verifier)
            )
            or not secrets.compare_digest(state, stored_state)
        ):
            raise ValueError()
    except (ValueError, TypeError):
        raise google_state_error(
            "OAUTH_BROWSER_STATE_MISSING", "Google sign-in expired or was not initiated in this browser."
        ) from None
    attempt = db.scalar(select(OAuthAttempt).where(OAuthAttempt.id == digest(state)).with_for_update())
    if (
        not attempt
        or attempt.expires_at.replace(tzinfo=now().tzinfo) <= now()
        or not secrets.compare_digest(attempt.nonce_hash, digest(nonce))
        or not secrets.compare_digest(attempt.verifier_hash, digest(verifier))
    ):
        raise google_state_error("OAUTH_STATE_INVALID", "Google sign-in state is invalid or expired.")
    link_user_id = attempt.link_user_id
    db.delete(attempt)
    db.commit()  # Consume once even if code exchange fails.
    if error:
        raise google_state_error(
            "OAUTH_CANCELLED", "Google sign-in was cancelled or could not be authorized. Start again."
        )
    try:
        claims = google_claims(code, verifier, nonce)
    except GoogleVerificationError as exc:
        audit(db, "oauth", "oauth.failed." + exc.reason.lower(), request.state.request_id)
        db.commit()
        raise
    ident = db.get(OAuthIdentity, claims["sub"])
    if link_user_id:
        cookie = request.cookies.get("veriora_session", "")
        session = db.get(Session, digest(cookie)) if cookie else None
        if (
            not session
            or session.user_id != link_user_id
            or session.expires_at.replace(tzinfo=now().tzinfo) <= now()
        ):
            raise HTTPException(403, "Sign in again before linking Google.")
        user = db.get(User, link_user_id)
        if user.email != claims["email"] or (ident and ident.user_id != user.id):
            raise HTTPException(409, "Google identity cannot be linked to this account.")
    elif ident:
        user = db.get(User, ident.user_id)
    else:
        if db.scalar(select(User).where(User.email == claims["email"])):
            response = RedirectResponse(
                settings().public_url + "/sign-in?oauth=link_required", status_code=303
            )
            clear_google_cookie(response)
            return response
        user = User(email=claims["email"], verified_at=now())
        db.add(user)
        db.flush()
    if not ident:
        db.add(OAuthIdentity(id=claims["sub"], user_id=user.id))
    prior = request.cookies.get("veriora_session", "")
    if prior:
        db.execute(delete(Session).where(Session.id == digest(prior)))
    response = RedirectResponse(settings().public_url + "/dashboard", status_code=303)
    create_session(db, user, response)
    clear_google_cookie(response)
    audit(db, user.id, "account.google_linked" if link_user_id else "account.google_login", user.id)
    db.commit()
    return response


@router.patch("/me/language", response_model=ProfileResponse)
def set_language(data: LanguageInput, request: Request, db: Db, user: CurrentUser):
    user.language = data.language
    db.commit()
    return profile(user, request.state.session.csrf)


@router.post("/auth/registration/start", status_code=202)
def registration_start(data: EmailRequest, request: Request, db: Db):
    throttle(db, "signup-ip:" + (request.client.host if request.client else "unknown"), 5, 3600)
    email = str(data.email).lower()
    throttle(db, "signup-email:" + email, 3, 3600)
    if not settings().smtp_host or not settings().mail_from:
        raise HTTPException(503, "Email delivery is not configured. Registration is unavailable.")
    message = {"message": "If this address can be registered, a verification link will be sent."}
    if db.scalar(select(User).where(User.email == email)):
        return message
    pending = db.scalar(
        select(PendingRegistration).where(PendingRegistration.email == email).with_for_update()
    )
    if pending and pending.expires_at.replace(tzinfo=now().tzinfo) > now():
        return message
    if pending:
        db.delete(pending)
        db.flush()
    cookie = request.cookies.get("veriora_session", "")
    session = db.get(Session, digest(cookie)) if cookie else None
    guest = db.get(User, session.user_id) if session else None
    valid_guest = guest and guest.is_guest and session.expires_at.replace(tzinfo=now().tzinfo) > now()
    if valid_guest and not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.csrf):
        raise HTTPException(403, "Reload your session and retry.")
    token = secrets.token_urlsafe(32)
    db.add(
        PendingRegistration(
            id=digest(token),
            email=email,
            password_hash="",
            expires_at=now() + timedelta(hours=1),
            guest_id=guest.id if valid_guest else None,
            session_hash=session.id if valid_guest else None,
        )
    )
    try:
        deliver(email, "signup", token)
    except HTTPException:
        db.rollback()
        return message
    db.commit()
    return message


@router.post("/auth/registration/verify")
def registration_verify(data: TokenRequest, request: Request, db: Db):
    throttle(db, "signup-verify:" + (request.client.host if request.client else "unknown"), 10, 900)
    pending = db.scalar(
        select(PendingRegistration).where(PendingRegistration.id == digest(data.token)).with_for_update()
    )
    if (
        not pending
        or pending.password_hash
        or pending.verified_at
        or pending.expires_at.replace(tzinfo=now().tzinfo) <= now()
    ):
        raise HTTPException(400, "Verification link is invalid or expired.")
    setup = secrets.token_urlsafe(32)
    # Rotating the primary key consumes the email token; only the hashed setup capability remains.
    pending.id = digest(setup)
    pending.verified_at = now()
    pending.expires_at = now() + timedelta(minutes=15)
    db.commit()
    return {"setup_token": setup, "message": "Email verified. Create your password to finish."}


@router.post("/auth/registration/complete", status_code=201)
def registration_complete(data: RegistrationComplete, request: Request, db: Db):
    throttle(db, "signup-complete:" + (request.client.host if request.client else "unknown"), 10, 900)
    if not secrets.compare_digest(data.password.encode(), data.confirm_password.encode()):
        raise HTTPException(422, "Passwords do not match.")
    pending = db.scalar(
        select(PendingRegistration).where(PendingRegistration.id == digest(data.token)).with_for_update()
    )
    if (
        not pending
        or not pending.verified_at
        or pending.password_hash
        or pending.expires_at.replace(tzinfo=now().tzinfo) <= now()
    ):
        raise HTTPException(400, "Password setup is invalid or expired. Request another verification link.")
    if db.scalar(select(User).where(User.email == pending.email)):
        raise HTTPException(400, "This registration cannot be completed. Sign in or recover access.")
    encoded = hasher.hash(data.password)
    cookie = request.cookies.get("veriora_session", "")
    prior = db.get(Session, digest(cookie)) if cookie else None
    guest = db.get(User, pending.guest_id) if pending.guest_id else None
    if (
        guest
        and guest.is_guest
        and prior
        and prior.id == pending.session_hash
        and prior.user_id == guest.id
        and prior.expires_at.replace(tzinfo=now().tzinfo) > now()
    ):
        if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), prior.csrf):
            raise HTTPException(403, "Reload your session and retry.")
        user = guest
        user.email = pending.email
        user.password_hash = encoded
        user.is_guest = False
        user.retention_days = 30
        for source in db.scalars(select(Source).where(Source.owner_id == user.id, Source.expires_at > now())):
            source.expires_at = source.captured_at.replace(tzinfo=now().tzinfo) + timedelta(days=30)
        db.execute(delete(Session).where(Session.user_id == user.id))
    else:
        user = User(email=pending.email, password_hash=encoded)
        db.add(user)
    user.verified_at = now()
    db.flush()
    db.delete(pending)
    audit(db, user.id, "account.email_verified", user.id)
    db.commit()
    return {"message": "Account created. Sign in to continue."}
