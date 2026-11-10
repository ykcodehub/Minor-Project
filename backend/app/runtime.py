"""Ephemeral process-health metadata only; never document or credential storage."""

import json
import os
import threading
import time
from pathlib import Path


def worker_heartbeat():
    value = os.environ.get("VERIORA_WORKER_HEALTH_FILE")
    if not value:
        return
    target = Path(value)
    temporary = target.with_name(target.name + f".{threading.get_ident()}.tmp")
    try:
        temporary.write_text(json.dumps({"pid": os.getpid(), "time": time.time()}), encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def worker_ready(max_age=90):
    if os.environ.get("VERIORA_COMBINED_SERVICE") != "1":
        return True  # Standalone API remains supported with separately supervised workers.
    try:
        data = json.loads(Path(os.environ["VERIORA_WORKER_HEALTH_FILE"]).read_text(encoding="utf-8"))
        return 0 <= time.time() - data["time"] <= max_age and data["pid"] > 0
    except (OSError, KeyError, ValueError, TypeError):
        return False
