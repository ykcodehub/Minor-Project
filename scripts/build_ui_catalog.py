"""Explicit build-time translation of PUBLIC UI COPY only; never reads user documents."""

import json
import sys
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import settings
from app.providers.base import ProviderError, generate_with_fallback


def stable_generate(*args):
    for attempt in range(4):
        try:
            return generate_with_fallback(*args)
        except ProviderError as exc:
            if (
                exc.code
                not in {
                    "PROVIDER_RATE_LIMITED",
                    "PROVIDER_REQUEST_REJECTED",
                    "PROVIDER_UNAVAILABLE",
                }
                or attempt == 3
            ):
                raise
            print("Catalog retry: " + exc.code, flush=True)
            time.sleep(20 if exc.code == "PROVIDER_RATE_LIMITED" else 3)


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: int
    hi: str
    hinglish: str


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    messages: list[Message] = Field(max_length=25)


def main():
    target = ROOT / "scripts/ui-catalog.partial.json"
    catalog = json.loads((target if target.exists() else ROOT / "frontend/src/lib/messages.json").read_text(encoding="utf-8"))
    keys = json.loads(
        (ROOT / "frontend/src/lib/ui-keys.json").read_text(encoding="utf-8")
    )
    todo = [k for k in keys if k not in catalog]
    provider = sys.argv[1] if len(sys.argv) > 1 else "groq"
    providers = [
        p
        for p in settings().providers()
        if p["name"] == provider and p["key"] and p["model"]
    ]
    for offset in range(0, len(todo), 6):
        chunk = todo[offset : offset + 6]
        try:
            result, _ = stable_generate(
                providers,
                "Translate public software UI copy accurately. Return JSON only. Hindi must be natural Devanagari. Hinglish must be natural Roman Hindi mixed with English. Preserve safety/privacy caveats, numbers, negation and product/provider names. Never add claims.",
                json.dumps(
                    [{"id": i, "text": text} for i, text in enumerate(chunk)],
                    ensure_ascii=False,
                ),
                Batch,
                "public_ui_catalog",
            )
            if len(result.messages) != len(chunk) or {
                m.id for m in result.messages
            } != set(range(len(chunk))):
                raise ValueError("ID mismatch")
            for message in result.messages:
                if not message.hi.strip() or not message.hinglish.strip():
                    raise ValueError("Empty message")
                catalog[chunk[message.id]] = {
                    "hi": message.hi,
                    "hinglish": message.hinglish,
                }
            target.write_text(
                json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Catalog entries: {len(catalog)}/{len(keys)}", flush=True)
        except (ProviderError, ValueError) as exc:
            print(
                "Catalog blocked: " + getattr(exc, "code", "INVALID_TRANSLATION"),
                flush=True,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
