"""Production guards, encrypted object adapter and reset approval gates; no remote services/reset."""

import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.config import Settings, settings
from app.reset_documents import validate_approval
from app.services import storage
from app.services.summary import suggested_questions


def test_production_rejects_local_storage_and_localhost():
    data = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql://fixture:fixture@db.example.com/prod",
        "storage_key": Fernet.generate_key().decode(),
        "secure_cookies": True,
    }
    with pytest.raises(ValidationError):
        Settings(**data)
    with pytest.raises(ValidationError):
        Settings(**data, storage_backend="s3", s3_bucket="private")
    cfg = Settings(
        **data,
        storage_backend="s3",
        s3_bucket="private",
        public_url="https://app.example.com",
        allowed_origins="https://app.example.com",
    )
    assert cfg.storage_backend == "s3"


def test_s3_roundtrip_encrypts_and_never_uses_local_storage(client, monkeypatch, tmp_path):
    cfg = settings()
    monkeypatch.setattr(cfg, "storage_backend", "s3")
    monkeypatch.setattr(cfg, "s3_bucket", "synthetic-private")
    objects = {}
    calls = []

    class S3:
        def put_object(self, **kwargs):
            calls.append(kwargs)
            objects[kwargs["Key"]] = kwargs["Body"]

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(objects[kwargs["Key"]])}

        def delete_object(self, **kwargs):
            objects.pop(kwargs["Key"], None)

    monkeypatch.setattr(storage, "s3_client", lambda: S3())
    original = b"Private contract fixture"
    key, digest = storage.write(original, "source-fixture")
    assert original not in next(iter(objects.values()))
    assert calls[0]["IfNoneMatch"] == "*" and calls[0]["ServerSideEncryption"] == "AES256"
    assert not cfg.storage_path.exists()
    assert storage.read(key, digest) == original
    storage.remove(key)
    assert not objects


def test_s3_deletion_failure_is_retryable_not_false_success(client, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "storage_backend", "s3")
    monkeypatch.setattr(cfg, "s3_bucket", "private")

    class S3:
        def delete_object(self, **kw):
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "sensitive-provider-detail"}}, "DeleteObject"
            )

    monkeypatch.setattr(storage, "s3_client", lambda: S3())
    with pytest.raises(OSError) as error:
        storage.remove("source.enc")
    assert "sensitive-provider-detail" not in str(error.value)
    with pytest.raises(ValueError):
        storage.read("../private.enc", "0" * 64)


def test_reset_refuses_production_without_touching_database(tmp_path):
    cfg = SimpleNamespace(environment="production")
    args = SimpleNamespace(
        environment="staging", confirm="DELETE DOCUMENTS fixture", backup_file=None, approval_file=None
    )
    with pytest.raises(ValueError, match="Production reset is prohibited"):
        validate_approval(cfg, args, "fixture")
    cfg.environment = "staging"
    with pytest.raises(ValueError, match="backup"):
        validate_approval(cfg, args, "fixture")
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"synthetic backup file")
    args.backup_file = backup
    with pytest.raises(ValueError, match="approval"):
        validate_approval(cfg, args, "fixture")


def test_vercel_rewrites_api_before_spa_and_refuses_localhost():
    path = Path(__file__).resolve().parents[2] / "scripts/prepare_vercel.py"
    spec = importlib.util.spec_from_file_location("prepare_vercel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = module.configuration("https://api.example.com")
    assert config["rewrites"][0]["destination"] == "https://api.example.com/api/:path*"
    assert config["rewrites"][1]["destination"] == "/index.html"
    for origin in ("http://localhost:8000", "https://127.0.0.2", "https://api.localhost"):
        with pytest.raises(ValueError):
            module.configuration(origin)


def test_suggested_questions_require_actual_supported_categories():
    assert suggested_questions([], "en") == []
    finding = {
        "category": "PAYMENT",
        "support_status": "UNSUPPORTED",
        "citations": [{"match_status": "EXACT"}],
    }
    assert suggested_questions([finding], "en") == []
    finding["support_status"] = "SUPPORTED"
    for language in ("en", "hi", "hinglish"):
        assert len(suggested_questions([finding], language)) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_url": "postgresql://fixture:fixture@127.0.0.2/db"},
        {"s3_endpoint_url": "https://localhost"},
        {"public_url": "https://app.localhost"},
        {"allowed_origins": "https://app.example.com/path"},
        {
            "google_client_id": "fixture",
            "google_redirect_uri": "https://localhost/api/v1/auth/google/callback",
        },
    ],
)
def test_production_rejects_environment_specific_loopback_targets(overrides):
    data = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql://fixture:fixture@db.example.com/db",
        "storage_backend": "s3",
        "s3_bucket": "private",
        "storage_key": Fernet.generate_key().decode(),
        "secure_cookies": True,
        "public_url": "https://app.example.com",
        "allowed_origins": "https://app.example.com",
    }
    with pytest.raises(ValidationError):
        Settings(**(data | overrides))
