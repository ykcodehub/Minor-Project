import hashlib
import secrets
from datetime import timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DB

from app.config import settings
from app.db import session
from app.models import RateBucket, Session, User, now

hasher = PasswordHasher()
DUMMY_PASSWORD_HASH = hasher.hash(secrets.token_urlsafe(32))
Db = Annotated[DB, Depends(session)]


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def authenticate(request: Request, db: Db):
    token = request.cookies.get("veriora_session", "")
    record = db.get(Session, digest(token)) if token else None
    if not record or record.expires_at.replace(tzinfo=now().tzinfo) <= now():
        raise HTTPException(401, "Please sign in or start a guest session.")
    user = db.get(User, record.user_id)
    if not user:
        raise HTTPException(401, "Session expired.")
    request.state.session = record
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(csrf, record.csrf):
            raise HTTPException(403, "Session validation failed. Reload and try again.")
    return user


CurrentUser = Annotated[User, Depends(authenticate)]


def create_session(db, user, response: Response):
    token = secrets.token_urlsafe(32)
    duration = timedelta(hours=24) if user.is_guest else timedelta(days=7)
    record = Session(
        id=digest(token), user_id=user.id, csrf=secrets.token_urlsafe(32), expires_at=now() + duration
    )
    db.add(record)
    response.set_cookie(
        "veriora_session",
        token,
        httponly=True,
        secure=settings().secure_cookies,
        samesite="lax",
        max_age=int(duration.total_seconds()),
        path="/",
    )
    return record


def password_valid(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, ValueError):
        return False


def throttle(db, key, limit=20, seconds=60):
    """Shared DB counter; increment is atomic across API processes."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    bucket = int(now().timestamp()) // seconds
    ident = f"{digest(key)}:{bucket}"
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    stmt = insert(RateBucket).values(id=ident, count=1, expires_at=now() + timedelta(seconds=seconds * 2))
    stmt = stmt.on_conflict_do_update(index_elements=[RateBucket.id], set_={"count": RateBucket.count + 1})
    db.execute(stmt)
    count = db.scalar(select(RateBucket.count).where(RateBucket.id == ident))
    db.commit()
    if count > limit:
        raise HTTPException(429, "Request limit reached. Please try again later.")
