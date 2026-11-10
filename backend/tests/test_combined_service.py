"""Supervisor and queue recovery regressions. Synthetic local processes/data only."""

import json
import os
import sys
import threading
import time
from datetime import timedelta

import pytest

from app import runtime
from app.serve import supervise


def test_supervisor_stops_api_when_worker_exits():
    stop = threading.Event()
    assert (
        supervise(
            {
                "api": [sys.executable, "-c", "import time;time.sleep(30)"],
                "worker": [sys.executable, "-c", "raise SystemExit(7)"],
            },
            stop,
            grace=0.2,
        )
        == 1
    )
    assert stop.is_set()


def test_supervisor_gracefully_stops_both_on_shutdown():
    stop = threading.Event()
    timer = threading.Timer(0.4, stop.set)
    timer.start()
    try:
        assert (
            supervise(
                {
                    "api": [sys.executable, "-c", "import time;time.sleep(30)"],
                    "worker": [sys.executable, "-c", "import time;time.sleep(30)"],
                },
                stop,
                grace=0.3,
            )
            == 0
        )
    finally:
        timer.cancel()


def test_combined_readiness_requires_recent_worker_heartbeat(monkeypatch, tmp_path):
    target = tmp_path / "worker.json"
    monkeypatch.setenv("VERIORA_COMBINED_SERVICE", "1")
    monkeypatch.setenv("VERIORA_WORKER_HEALTH_FILE", str(target))
    assert not runtime.worker_ready()
    runtime.worker_heartbeat()
    assert runtime.worker_ready()
    target.write_text(json.dumps({"pid": os.getpid(), "time": time.time() - 120}))
    assert not runtime.worker_ready()
    target.write_text("broken")
    assert not runtime.worker_ready()


def test_stale_extraction_updates_source_and_rejects_old_lease(client):
    from conftest import login_guest

    from app.db import SessionLocal
    from app.models import Job, Source, now
    from app.worker import LeaseLost, claim, progress

    login_guest(client)
    created = client.post(
        "/api/v1/sources/text",
        json={"name": "fixture.txt", "text": "Payment is required within thirty days."},
    ).json()
    with SessionLocal() as db:
        job = db.get(Job, created["job_id"])
        source = db.get(Source, created["source_id"])
        job.state, job.stage, job.lease_token = "PROCESSING", "PARSING", "old-token"
        job.lease_until = now() - timedelta(seconds=1)
        source.status = "PROCESSING"
        db.commit()
    assert claim() is None
    with SessionLocal() as db:
        job = db.get(Job, created["job_id"])
        assert job.state == "FAILED" and job.stage == "FAILED" and job.lease_until is None
        assert db.get(Source, created["source_id"]).status == "FAILED"
    with pytest.raises(LeaseLost):
        progress(created["job_id"], "old-token", "COMPLETED")
    # Existing explicit retry endpoint is preserved; recovery itself never replays AI.
    assert client.post(f"/api/v1/jobs/{created['job_id']}/retry").status_code == 200
    assert claim() is not None


def test_real_supervisor_api_and_worker_process_a_synthetic_upload(tmp_path):
    import socket

    import httpx
    from cryptography.fernet import Fernet
    from sqlalchemy import create_engine

    from app.db import Base
    from app.serve import service_commands

    target = tmp_path / "combined.db"
    engine = create_engine("sqlite:///" + target.as_posix())
    Base.metadata.create_all(engine)
    engine.dispose()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_URL": "sqlite:///" + target.as_posix(),
        "STORAGE_BACKEND": "filesystem",
        "STORAGE_KEY": Fernet.generate_key().decode(),
        "STORAGE_PATH": str(tmp_path / "objects"),
        "SECURE_COOKIES": "false",
        "SESSION_COOKIE_SAMESITE": "lax",
        "ALLOWED_ORIGINS": origin,
        "PUBLIC_URL": origin,
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "SMTP_HOST": "",
        "VERIORA_COMBINED_SERVICE": "1",
        "VERIORA_WORKER_HEALTH_FILE": str(tmp_path / "worker.json"),
    }
    env.pop("TEST_MAIL_OUTBOX", None)
    stop = threading.Event()
    result = []
    thread = threading.Thread(
        target=lambda: result.append(supervise(service_commands(port), stop, env=env, grace=2))
    )
    thread.start()
    try:
        with httpx.Client(base_url=origin, timeout=3, headers={"Origin": origin}) as browser:
            for _ in range(100):
                try:
                    if browser.get("/api/v1/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                pytest.fail("Combined API/worker failed readiness")
            user = browser.post("/api/v1/auth/guest")
            assert user.status_code == 201
            browser.headers["X-CSRF-Token"] = user.json()["csrf_token"]
            created = browser.post(
                "/api/v1/sources/text",
                json={"name": "smoke.txt", "text": "Payment is due within thirty days."},
            )
            assert created.status_code == 202
            source_id = created.json()["source_id"]
            for _ in range(80):
                state = browser.get(f"/api/v1/sources/{source_id}").json()
                if state["status"] not in {"QUEUED", "PROCESSING"}:
                    break
                time.sleep(0.2)
            assert state["status"] == "READY" and state["sections"]
            job = browser.get("/api/v1/jobs/" + created.json()["job_id"]).json()
            assert job["state"] == "COMPLETED" and job["attempts"] == 1
    finally:
        stop.set()
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert result == [0]
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
