"""Leave real local API/worker/Vite running against disposable synthetic-only storage.

Never reads database/provider secrets into the child configuration. No real email or AI.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-port", type=int, default=5173)
    args = parser.parse_args()
    if not 1024 <= args.frontend_port <= 65535:
        raise RuntimeError("Frontend port must be from 1024 to 65535.")
    origin = f"http://127.0.0.1:{args.frontend_port}"
    for port in (8000, args.frontend_port):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(
                    f"Port {port} is occupied; no existing process was stopped."
                )
    runtime = ROOT / "backend/private-data" / ("local-synthetic-" + uuid.uuid4().hex)
    runtime.mkdir(parents=True)
    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_URL": "sqlite:///" + (runtime / "test.db").as_posix(),
        "STORAGE_BACKEND": "filesystem",
        "STORAGE_PATH": str(runtime / "objects"),
        "STORAGE_KEY": Fernet.generate_key().decode(),
        "GEMINI_API_KEY": "",
        "GROQ_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "GOOGLE_REDIRECT_URI": origin + "/api/v1/auth/google/callback",
        "SMTP_HOST": "test-capture.invalid",
        "SMTP_PASSWORD": "",
        "MAIL_FROM": "synthetic@example.com",
        "TEST_MAIL_OUTBOX": str(runtime / "mail.jsonl"),
        "PUBLIC_URL": origin,
        "ALLOWED_ORIGINS": origin,
        "SECURE_COOKIES": "false",
        "SESSION_COOKIE_SAMESITE": "lax",
        "VERIORA_WORKER_HEALTH_FILE": str(runtime / "worker.json"),
        "VERIORA_COMBINED_SERVICE": "1",
        "VITE_API_TARGET": "http://127.0.0.1:8000",
        "VITE_API_BASE_URL": "/api/v1",
        "PYTHONUNBUFFERED": "1",
    }
    processes = []
    options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    with (runtime / "services.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
        npm = ["cmd.exe", "/d", "/c", "npm"] if os.name == "nt" else ["npm"]
        try:
            for name, command, cwd in (
                (
                    "api",
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                    ],
                    ROOT / "backend",
                ),
                ("worker", [sys.executable, "-m", "app.worker"], ROOT / "backend"),
                (
                    "frontend",
                    [
                        *npm,
                        "run",
                        "dev",
                        "--",
                        "--port",
                        str(args.frontend_port),
                        "--strictPort",
                    ],
                    ROOT / "frontend",
                ),
            ):
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    **options,
                )
                processes.append((name, process))
            for url in ("http://127.0.0.1:8000/api/v1/ready", origin):
                for _ in range(90):
                    if any(p.poll() is not None for _, p in processes):
                        raise RuntimeError(
                            "A local service exited. Inspect the isolated services.log."
                        )
                    try:
                        with urllib.request.urlopen(url, timeout=2) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError(
                        "Local readiness timed out; inspect the isolated services.log."
                    )
        except Exception:
            for _, process in processes:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    process.terminate()
            raise
    manifest = {
        "mode": "isolated synthetic test; no live AI or production DB writes",
        "runtime": str(runtime),
        "processes": {name: p.pid for name, p in processes},
        "frontend": origin,
        "api": "http://127.0.0.1:8000",
        "mailbox": str(runtime / "mail.jsonl"),
    }
    (runtime / "running.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
