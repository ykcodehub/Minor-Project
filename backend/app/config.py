from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


POLICY_ERRORS = {
    "S3_CONFIGURATION_REQUIRED": "Configure S3_BUCKET and the existing stable STORAGE_KEY for S3 storage.",
    "S3_HTTPS_REQUIRED": "S3_ENDPOINT_URL must use HTTPS.",
    "S3_PREFIX_INVALID": "S3_PREFIX must be relative and cannot contain traversal or backslashes.",
    "PRODUCTION_STORAGE_REQUIRED": "Production requires STORAGE_BACKEND=s3 and TEST_MAIL_OUTBOX unset.",
    "PUBLIC_ORIGINS_INVALID": "PUBLIC_URL and ALLOWED_ORIGINS must be public HTTPS origins without credentials, paths or queries.",
    "PRODUCTION_ENDPOINT_INVALID": "DATABASE_URL and S3_ENDPOINT_URL cannot use missing or loopback hosts in production.",
    "GOOGLE_REDIRECT_INVALID": "GOOGLE_REDIRECT_URI must use the exact /api/v1/auth/google/callback path and HTTPS except local development.",
    "POSTGRES_DRIVER_REQUIRED": "DATABASE_URL must use PostgreSQL with psycopg; SQLite is restricted to isolated tests.",
}


class ConfigurationPolicyError(ValueError):
    """Static deployment guidance only; never include configured values in this exception."""

    def __init__(self, code):
        self.code = code
        super().__init__(code + ": " + POLICY_ERRORS[code])


def loopback_host(host):
    if not host:
        return True
    value = host.rstrip(".").lower()
    if value == "localhost" or value.endswith(".localhost"):
        return True
    try:
        return ip_address(value).is_loopback
    except ValueError:
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")
    database_url: str = Field(repr=False)
    storage_path: Path = Path("private-data")
    storage_key: str = Field(default="", repr=False)
    storage_backend: Literal["filesystem", "s3"] = "filesystem"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    s3_prefix: str = "veriora/"

    secure_cookies: bool = False
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    environment: str = "development"
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pages: int = 150
    max_document_tokens: int = 100000
    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = ""
    groq_api_key: str = Field(default="", repr=False)
    groq_model: str = ""
    openrouter_api_key: str = Field(default="", repr=False)
    openrouter_model: str = ""
    provider_pricing: dict[str, dict[str, float]] = Field(default_factory=dict)
    test_mail_outbox: Path | None = Field(default=None, repr=False)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = Field(default="", repr=False)
    mail_from: str = ""
    google_client_id: str = ""
    google_client_secret: str = Field(default="", repr=False)
    google_redirect_uri: str = "http://localhost:5173/api/v1/auth/google/callback"
    oauth_proxy_hosts: str = ""
    public_url: str = "http://localhost:5173"

    @field_validator("database_url", mode="before")
    @classmethod
    def postgres_driver(cls, value):
        if isinstance(value, str):
            for prefix in ("postgresql://", "postgres://"):
                if value.startswith(prefix):
                    return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @field_validator("storage_path")
    @classmethod
    def private_path(cls, value):
        return value if value.is_absolute() else BACKEND_ROOT / value

    @model_validator(mode="after")
    def database_policy(self):
        if self.storage_backend == "s3":
            from urllib.parse import urlsplit

            if not self.s3_bucket or not self.storage_key:
                raise ConfigurationPolicyError("S3_CONFIGURATION_REQUIRED")
            if self.s3_endpoint_url and urlsplit(self.s3_endpoint_url).scheme != "https":
                raise ConfigurationPolicyError("S3_HTTPS_REQUIRED")
            if ".." in self.s3_prefix or self.s3_prefix.startswith("/") or "\\" in self.s3_prefix:
                raise ConfigurationPolicyError("S3_PREFIX_INVALID")
        if self.environment == "production":
            from urllib.parse import urlsplit

            targets = [self.public_url, *[v.strip() for v in self.allowed_origins.split(",")]]
            if self.storage_backend != "s3" or self.test_mail_outbox:
                raise ConfigurationPolicyError("PRODUCTION_STORAGE_REQUIRED")
            for value in targets:
                target = urlsplit(value)
                if (
                    target.scheme != "https"
                    or not target.hostname
                    or loopback_host(target.hostname)
                    or target.username
                    or target.password
                    or target.query
                    or target.fragment
                    or target.path not in {"", "/"}
                ):
                    raise ConfigurationPolicyError("PUBLIC_ORIGINS_INVALID")

        if self.environment == "production":
            from urllib.parse import urlsplit

            for endpoint in filter(None, [self.database_url, self.s3_endpoint_url]):
                if loopback_host(urlsplit(endpoint).hostname):
                    raise ConfigurationPolicyError("PRODUCTION_ENDPOINT_INVALID")

        if self.google_client_id or self.google_client_secret:
            from urllib.parse import urlsplit

            target = urlsplit(self.google_redirect_uri)
            if (
                (self.environment == "production" and loopback_host(target.hostname))
                or target.username
                or target.password
                or target.query
                or target.fragment
                or target.path != "/api/v1/auth/google/callback"
                or target.scheme not in {"http", "https"}
                or (
                    target.scheme == "http"
                    and (
                        self.environment == "production" or target.hostname not in {"localhost", "127.0.0.1"}
                    )
                )
            ):
                raise ConfigurationPolicyError("GOOGLE_REDIRECT_INVALID")
        if not self.database_url.startswith("postgresql+psycopg://") and not (
            self.environment == "test" and self.database_url.startswith("sqlite")
        ):
            raise ConfigurationPolicyError("POSTGRES_DRIVER_REQUIRED")
        return self

    def providers(self):
        if self.environment == "test":
            # Do not inherit live provider credentials from .env in isolated test servers.
            return [{"name": n, "key": "", "model": ""} for n in ("gemini", "groq", "openrouter")]
        return [
            {
                "name": n,
                "key": getattr(self, n + "_api_key"),
                "model": getattr(self, n + "_model"),
                **{
                    k: v
                    for k, v in self.provider_pricing.get(n, {}).items()
                    if k in ("input_price_per_million", "output_price_per_million") and v >= 0
                },
            }
            for n in ("gemini", "groq", "openrouter")
        ]


@lru_cache
def settings():
    try:
        value = Settings()
    except ValidationError as exc:
        diagnostics = set()
        for error in exc.errors(include_input=False, include_url=False):
            policy = error.get("ctx", {}).get("error")
            if isinstance(policy, ConfigurationPolicyError) and policy.code in POLICY_ERRORS:
                diagnostics.add(policy.code + ": " + POLICY_ERRORS[policy.code])
            else:
                # Field names/types are safe; arbitrary exception text and input values are not.
                field = str(error["loc"][0]) if error["loc"] else "database_policy"
                diagnostics.add(field + ": " + error["type"])
        raise RuntimeError("Invalid application configuration: " + "; ".join(sorted(diagnostics))) from None
    if value.environment == "production" and (
        not value.secure_cookies or not value.storage_key or not value.database_url.startswith("postgresql")
    ):
        raise RuntimeError("Production requires secure cookies, storage encryption key and PostgreSQL")
    return value
