"""Read-only by default. Never automatically reset a production database.

Preferred production procedure: provision a fresh PostgreSQL database and migrate.
This guarded operator command removes document-derived records only after separate approval.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, inspect, select, text

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import Job, Report, Source, StorageDeletion

SCOPE = "documents-only"
PRESERVED = {
    "users",
    "sessions",
    "auth_tokens",
    "pending_registrations",
    "oauth_identities",
    "oauth_attempts",
    "rate_buckets",
    "audit_events",
    "storage_deletions",
    "alembic_version",
}


def database_fingerprint():
    target = "|".join(str(v or "") for v in (engine.url.host, engine.url.port, engine.url.database))
    return hashlib.sha256(target.encode()).hexdigest()[:16]


def validate_approval(cfg, args, fingerprint):
    if cfg.environment == "production":
        raise ValueError("Production reset is prohibited. Provision a fresh database.")
    if cfg.environment not in {"development", "staging"} or args.environment != cfg.environment:
        raise ValueError("Explicit development/staging environment must match current configuration.")
    if args.confirm != "DELETE DOCUMENTS " + fingerprint:
        raise ValueError("Target-specific confirmation is required.")
    if not args.backup_file or not args.backup_file.is_file() or args.backup_file.stat().st_size == 0:
        raise ValueError("A nonempty separately verified database backup file is required.")
    if not args.approval_file or not args.approval_file.is_file():
        raise ValueError("Separate user approval file is required.")
    approval = json.loads(args.approval_file.read_text(encoding="utf-8"))
    expiry = datetime.fromisoformat(approval.get("expires_at", ""))
    if (
        approval.get("approved") is not True
        or approval.get("backup_confirmed") is not True
        or approval.get("scope") != SCOPE
        or approval.get("environment") != cfg.environment
        or approval.get("database_fingerprint") != fingerprint
        or not approval.get("approved_by")
        or expiry.tzinfo is None
        or not datetime.now(UTC) < expiry <= datetime.now(UTC) + timedelta(hours=24)
    ):
        raise ValueError("Approval must match scope, environment, target and a future expiry within24 hours.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--environment", choices=["development", "staging"])
    parser.add_argument("--backup-file", type=Path)
    parser.add_argument("--approval-file", type=Path)
    parser.add_argument("--confirm")
    args = parser.parse_args()
    cfg = settings()
    if engine.dialect.name != "postgresql":
        raise SystemExit("This procedure requires PostgreSQL; no SQLite fallback.")
    fingerprint = database_fingerprint()
    with SessionLocal() as db:
        tables = set(inspect(engine).get_table_names())
        counts = {
            name: db.scalar(select(func.count()).select_from(table))
            for name, table in Base.metadata.tables.items()
            if name in tables
        }
        revision = db.scalar(text("SELECT version_num FROM alembic_version"))
        print(
            json.dumps(
                {
                    "mode": "plan",
                    "scope": SCOPE,
                    "database_fingerprint": fingerprint,
                    "environment": cfg.environment,
                    "revision": revision,
                    "document_records": {k: v for k, v in counts.items() if k not in PRESERVED},
                    "preserved_tables": sorted(PRESERVED),
                }
            )
        )
        if not args.execute:
            return
        try:
            validate_approval(cfg, args, fingerprint)
        except (ValueError, TypeError, KeyError):
            raise SystemExit(
                "Reset refused: verify environment, backup, separate approval and target confirmation."
            ) from None
        # Stop API and workers first; table locks prevent writes during this transaction.
        db.execute(text("LOCK TABLE sources, jobs, reports IN ACCESS EXCLUSIVE MODE"))
        if db.scalar(select(func.count()).select_from(Job).where(Job.state.in_(["QUEUED", "PROCESSING"]))):
            raise SystemExit("Reset refused: finish/cancel active jobs and stop API/workers first.")
        keys = list(db.scalars(select(Source.object_key))) + list(db.scalars(select(Report.object_key)))
        existing = set(db.scalars(select(StorageDeletion.object_key)))
        db.add_all([StorageDeletion(object_key=key) for key in set(keys) - existing])
        # FK cascades remove sections/chunks/findings/evidence/questions/reports/translations.
        # Never touch accounts, credentials, preferences, audits or migration history.
        db.execute(delete(Source))
        db.execute(delete(Job))
        db.commit()
        print(
            json.dumps(
                {
                    "status": "document_records_removed",
                    "physical_objects": "queued for separately supervised cleanup",
                    "schema_preserved": True,
                }
            )
        )


if __name__ == "__main__":
    main()
