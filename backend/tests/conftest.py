import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

from app.config import settings
from app.db import Base, SessionLocal
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "storage_path", tmp_path / "private")
    monkeypatch.setattr(cfg, "storage_key", Fernet.generate_key().decode())
    monkeypatch.setattr(cfg, "smtp_host", "")
    monkeypatch.setattr(cfg, "environment", "development")

    for provider in ("gemini", "groq", "openrouter"):
        monkeypatch.setattr(cfg, provider + "_api_key", "")
        monkeypatch.setattr(cfg, provider + "_model", "")
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "test.db"), connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    previous = SessionLocal.kw["bind"]
    SessionLocal.configure(bind=engine)
    mail = []

    def capture(email, purpose, token):
        mail.append({"email": email, "purpose": purpose, "token": token})

    monkeypatch.setattr("app.api.auth.deliver", capture)
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=True) as test:
        test.veriora_mail = mail
        test.headers["Origin"] = "http://localhost:5173"
        yield test
    SessionLocal.configure(bind=previous)
    engine.dispose()


def login_guest(client):
    response = client.post("/api/v1/auth/guest")
    assert response.status_code == 201, response.text
    data = response.json()
    client.headers["X-CSRF-Token"] = data["csrf_token"]
    return data
