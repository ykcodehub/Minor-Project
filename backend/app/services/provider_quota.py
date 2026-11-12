"""Shared provider cooldowns in existing rate buckets; no keys or response prose stored."""

import hashlib
import math
from datetime import timedelta

from sqlalchemy import func

from app.models import RateBucket, now


def hooks(config, factory, *, category="quota"):
    ident = ("ai-cooldown:" if category == "quota" else "ai-outage:") + hashlib.sha256(
        (config["name"] + "|" + config["model"] + "|" + config["key"]).encode()
    ).hexdigest()

    def check():
        with factory() as db:
            row = db.get(RateBucket, ident)
            return (
                max(0, math.ceil((row.expires_at.replace(tzinfo=now().tzinfo) - now()).total_seconds()))
                if row
                else 0
            )

    def block(seconds):
        seconds = seconds if math.isfinite(seconds) and 0 < seconds <= 31536000 else 60
        with factory() as db:
            if db.bind.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert

                greatest = func.greatest
            else:
                from sqlalchemy.dialects.sqlite import insert

                greatest = func.max
            stmt = insert(RateBucket).values(
                id=ident,
                count=429 if category == "quota" else 503,
                expires_at=now() + timedelta(seconds=seconds),
            )
            db.execute(
                stmt.on_conflict_do_update(
                    index_elements=[RateBucket.id],
                    set_={
                        "expires_at": greatest(RateBucket.expires_at, stmt.excluded.expires_at),
                        "count": 429 if category == "quota" else 503,
                    },
                )
            )
            db.commit()

    return check, block
