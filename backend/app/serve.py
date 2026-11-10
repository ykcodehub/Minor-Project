"""One API + one durable worker for a single small web-service instance."""

import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time

log = logging.getLogger("veriora.supervisor")


def stop_child(child, hard=False):
    if child.poll() is not None:
        return
    try:
        if os.name == "nt":
            # Windows venv launchers can own an interpreter child: terminate the owned tree.
            subprocess.run(
                ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            os.killpg(child.pid, signal.SIGKILL if hard else signal.SIGTERM)
    except ProcessLookupError:
        pass


def supervise(commands, stop, env=None, grace=25):
    children = {}
    failed = False
    try:
        for name, command in commands.items():
            options = (
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            children[name] = subprocess.Popen(command, env=env, **options)
            log.info("started service=%s pid=%s", name, children[name].pid)
        while not stop.wait(0.25):
            for name, child in children.items():
                if child.poll() is not None:
                    log.error(
                        "unexpected exit service=%s exit_code=%s; stopping companion", name, child.returncode
                    )
                    failed = True
                    stop.set()
                    break
    finally:
        for child in children.values():
            stop_child(child)
        deadline = time.monotonic() + grace
        for name, child in children.items():
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                log.warning(
                    "grace expired service=%s; forcing shutdown; job lease recovery remains active", name
                )
                stop_child(child, hard=True)
                child.wait(timeout=5)
    return 1 if failed else 0


def service_commands(port):
    return {
        "api": [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--workers",
            "1",
            "--timeout-graceful-shutdown",
            "20",
        ],
        "worker": [sys.executable, "-m", "app.worker"],
    }


def main():
    from app.config import settings

    settings()  # Fail with existing redacted policy diagnostics before spawning either service.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    port = os.environ.get("PORT", "8000")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise SystemExit("PORT must be an integer from1 to65535")
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    with tempfile.TemporaryDirectory(prefix="veriora-runtime-") as runtime:
        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "VERIORA_COMBINED_SERVICE": "1",
            "VERIORA_WORKER_HEALTH_FILE": os.path.join(runtime, "worker.json"),
        }
        # Limit native allocator/thread overhead; do not override explicit operator values.
        env.setdefault("OMP_NUM_THREADS", "1")
        env.setdefault("MALLOC_ARENA_MAX", "2")
        commands = service_commands(port)
        raise SystemExit(supervise(commands, stop, env=env))


if __name__ == "__main__":
    main()
