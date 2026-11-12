"""Run browser regressions against temporary local storage; never the configured PostgreSQL data."""

import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wait_for(url, process):
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError(
                "A test service exited; inspect its isolated service log."
            )
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Isolated test service did not become ready.")


def npm(*args):
    return ["cmd.exe", "/d", "/c", "npm", *args] if os.name == "nt" else ["npm", *args]


def main():
    for port in (8002, 5174):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(
                    f"Test port {port} is already occupied. Stop only your prior test instance."
                )
    runtime = ROOT / "backend" / "private-data" / ("e2e-" + uuid.uuid4().hex)
    runtime.mkdir(parents=True)
    executable = (
        ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    if not executable.exists():
        executable = Path(sys.executable)
    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_URL": "sqlite:///" + (runtime / "test.db").as_posix(),
        "STORAGE_PATH": str(runtime / "objects"),
        "SECURE_COOKIES": "false",
        "SMTP_HOST": "test-capture.invalid",
        "MAIL_FROM": "synthetic@example.com",
        "TEST_MAIL_OUTBOX": str(runtime / "mail.jsonl"),
        "VERIORA_TEST_MAILBOX": str(runtime / "mail.jsonl"),
        "GEMINI_API_KEY": "",
        "GROQ_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "ALLOWED_ORIGINS": "http://localhost:5174,http://127.0.0.1:5174",
        "VITE_API_TARGET": "http://127.0.0.1:8002",
        "E2E_BASE_URL": "http://127.0.0.1:5174",
        "VERIORA_LIVE_E2E": "0",
        "VERIORA_TEST_ISOLATED": "1",
    }
    # A separate key is supplied through the environment, not through a shell or command argument.
    generated = subprocess.check_output(
        [
            str(executable),
            "-c",
            "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())",
        ],
        text=True,
    )
    env["STORAGE_KEY"] = generated.strip()
    processes = []
    with (runtime / "services.log").open("w", encoding="utf-8") as log:
        try:
            subprocess.run(
                [str(executable), "-m", "alembic", "upgrade", "head"],
                cwd=ROOT / "backend",
                env=env,
                check=True,
            )
            for command, cwd in [
                (
                    [
                        str(executable),
                        "-m",
                        "uvicorn",
                        "oauth_browser_fixture:app",
                        "--app-dir",
                        str(ROOT / "scripts"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8002",
                    ],
                    ROOT / "backend",
                ),
                ([str(executable), "-m", "app.worker"], ROOT / "backend"),
                (
                    npm("run", "dev", "--", "--port", "5174", "--strictPort"),
                    ROOT / "frontend",
                ),
            ]:
                processes.append(
                    subprocess.Popen(
                        command,
                        cwd=cwd,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        **(
                            {"creationflags": subprocess.CREATE_NO_WINDOW}
                            if os.name == "nt"
                            else {"start_new_session": True}
                        ),
                    )
                )
            wait_for("http://127.0.0.1:8002/api/v1/ready", processes[0])
            wait_for("http://127.0.0.1:5174", processes[2])
            command = (
                ["cmd.exe", "/d", "/c", "npx", "playwright", "test"]
                if os.name == "nt"
                else ["npx", "playwright", "test"]
            )
            result = subprocess.run(
                [*command, *sys.argv[1:]], cwd=ROOT / "frontend", env=env, check=False
            )
            return result.returncode
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    else:
                        import signal

                        os.killpg(process.pid, signal.SIGTERM)
            print("Isolated browser service log:", runtime / "services.log")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("Browser test setup failed:", str(exc))
        raise SystemExit(1) from None
