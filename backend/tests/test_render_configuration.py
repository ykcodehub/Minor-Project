"""Render production diagnostics and R2 compatibility. No remote/database calls."""

import io

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app import config
from app.services import storage


def production(**overrides):
    values = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql://fixture:fixture@ep-fixture.ap-southeast-1.aws.neon.tech/fixture?sslmode=require&channel_binding=require",
        "storage_backend": "s3",
        "s3_bucket": "private-fixture",
        "storage_key": Fernet.generate_key().decode(),
        "s3_endpoint_url": "https://fixture.r2.cloudflarestorage.com",
        "s3_region": "auto",
        "secure_cookies": True,
        "public_url": "https://app.example.com",
        "allowed_origins": "https://app.example.com",
        "google_client_id": "",
        "google_client_secret": "",
        "test_mail_outbox": None,
    }
    return config.Settings(**(values | overrides))


def test_neon_r2_production_settings_pass_without_network(monkeypatch):
    cfg = production()
    assert cfg.database_url.startswith("postgresql+psycopg://")
    assert cfg.s3_region == "auto"
    monkeypatch.setattr(config, "Settings", lambda: cfg)
    assert config.settings.__wrapped__() is cfg


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"storage_backend": "filesystem"}, "PRODUCTION_STORAGE_REQUIRED"),
        ({"s3_bucket": ""}, "S3_CONFIGURATION_REQUIRED"),
        ({"storage_key": ""}, "S3_CONFIGURATION_REQUIRED"),
        ({"public_url": "http://localhost:5173"}, "PUBLIC_ORIGINS_INVALID"),
        ({"allowed_origins": "https://app.example.com,"}, "PUBLIC_ORIGINS_INVALID"),
        ({"s3_endpoint_url": "http://fixture.r2.cloudflarestorage.com"}, "S3_HTTPS_REQUIRED"),
        ({"s3_prefix": "../SECRET_CANARY"}, "S3_PREFIX_INVALID"),
        (
            {
                "google_client_id": "fixture",
                "google_redirect_uri": "http://localhost:5173/api/v1/auth/google/callback",
            },
            "GOOGLE_REDIRECT_INVALID",
        ),
    ],
)
def test_startup_identifies_policy_without_logging_values(monkeypatch, overrides, code):
    # Construct the ValidationError first, so settings() exercises its real public wrapper.
    with pytest.raises(ValidationError) as failure:
        production(**overrides)

    def invalid_settings():
        raise failure.value

    monkeypatch.setattr(config, "Settings", invalid_settings)
    with pytest.raises(RuntimeError) as error:
        config.settings.__wrapped__()
    message = str(error.value)
    assert code in message
    assert "SECRET_CANARY" not in message
    assert "fixture.r2.cloudflarestorage.com" not in message
    assert "postgresql://" not in message
    assert error.value.__suppress_context__


def test_unexpected_validation_error_never_serializes_input(monkeypatch):
    with pytest.raises(ValidationError) as failure:
        production(secure_cookies="SECRET_CANARY")

    def invalid_settings():
        raise failure.value

    monkeypatch.setattr(config, "Settings", invalid_settings)
    with pytest.raises(RuntimeError, match="secure_cookies: bool_parsing") as error:
        config.settings.__wrapped__()
    assert "SECRET_CANARY" not in str(error.value)


def test_secure_cookies_still_required(monkeypatch):
    cfg = production(secure_cookies=False)
    monkeypatch.setattr(config, "Settings", lambda: cfg)
    with pytest.raises(RuntimeError, match="Production requires secure cookies"):
        config.settings.__wrapped__()


def test_r2_upload_preserves_encryption_and_conditional_write(client, monkeypatch):
    cfg = config.settings()
    monkeypatch.setattr(cfg, "storage_backend", "s3")
    monkeypatch.setattr(cfg, "s3_bucket", "private-fixture")
    monkeypatch.setattr(cfg, "s3_endpoint_url", "https://fixture.r2.cloudflarestorage.com")
    objects = {}

    class R2:
        def put_object(self, **kwargs):
            assert "ServerSideEncryption" not in kwargs
            assert kwargs["IfNoneMatch"] == "*"
            assert b"private contract" not in kwargs["Body"]
            objects[kwargs["Key"]] = kwargs["Body"]

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(objects[kwargs["Key"]])}

    monkeypatch.setattr(storage, "s3_client", lambda: R2())
    key, digest = storage.write(b"private contract", "fixture")
    assert storage.read(key, digest) == b"private contract"
    assert not cfg.storage_path.exists()
