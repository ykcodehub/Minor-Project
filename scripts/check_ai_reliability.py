"""Opt-in, zero-price synthetic smoke check. No database or storage access.

Run with the repository virtualenv. Only the existing explicit OpenRouter :free
model is eligible; this never substitutes models or assumes a billed API is free.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings
from app.providers.base import ProviderError, configured_provider
from app.providers.model_policy import DYNAMIC_MODELS, model_info
from app.services.analysis import analyze
from app.services.chunking import chunk_sections
from app.services.summary import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-provider", choices=["openrouter"], help="Explicit synthetic-test consent")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = {"synthetic_only": True, "production_data_access": False, "results": []}
    try:
        configs = Settings().providers()
    except ValueError:
        # Pydantic configuration exceptions can contain secrets; never stringify them.
        report["configuration"] = "BLOCKED_INVALID_CONFIGURATION"
        configs = []
    for config in configs:
        provider, model = config["name"], config["model"]
        row = {
            "provider": provider,
            "model": re.sub(r"[^A-Za-z0-9/._:-]", "", model)[:160],
            "status": "BLOCKED",
            "inference_requests": 0,
            "token_in": None,
            "token_out": None,
            "reasoning_tokens": None,
            "latency_ms": None,
            "evidence_coverage": None,
        }
        report["results"].append(row)
        if provider != "openrouter":
            row["reason"] = "Zero billing cannot be established; paid usage not authorized."
            continue
        if not config["key"] or not model.endswith(":free") or model in DYNAMIC_MODELS:
            row["reason"] = (
                "An existing explicit :free model and credential are required; no model substituted."
            )
            continue
        if args.allow_provider != provider:
            row["reason"] = "Explicit synthetic-test provider consent required."
            continue
        started = time.perf_counter()
        calls = []
        try:
            info = model_info(model)
            if any(str(info.get("pricing", {}).get(k)) not in {"0", "0.0"} for k in ("prompt", "completion")):
                raise ProviderError("ZERO_PRICE_NOT_CONFIRMED")
            config = {
                **config,
                "operation": "synthetic_smoke",
                "retries": 0,
                "request_tokens": min(config.get("request_tokens", 6000), 6000),
                "max_output_tokens": min(config.get("max_output_tokens", 2048), 2048),
                "budget": {
                    "calls": 0,
                    "tokens": 0,
                    "max_calls": 4,
                    "max_tokens": 16000,
                    "deadline": time.monotonic() + 90,
                },
                "authorize": lambda: args.allow_provider == "openrouter",
            }
            # Capability preflight before any inference reservation.
            p = configured_provider(config)
            if not p.fits("Source-only analysis", "Payment is due within thirty days.", {"type": "object"}):
                raise ProviderError("PROVIDER_MODEL_INCOMPATIBLE")
            sections = [
                {
                    "id": "synthetic-section",
                    "source_id": "synthetic-source",
                    "page": 1,
                    "text": "Invoices must be paid within thirty days. No late fee applies during a genuine invoice dispute.",
                }
            ]
            result = analyze(chunk_sections(sections), sections, [config])
            calls = result["model_calls"]
            partial = result["partial"]
            summary = summarize(
                result["findings"],
                sections,
                result["coverage"],
                "PARTIAL_COMPLETION" if partial else "COMPLETED",
            )
            row.update(
                status="PARTIAL_COMPLETION" if partial else "COMPLETED",
                evidence_coverage=result["coverage"],
                verified_findings=sum(f["support_status"] == "SUPPORTED" for f in result["findings"]),
                summary_level=summary["level"],
            )
        except ProviderError as exc:
            calls = exc.model_calls
            row.update(status="FAIL", reason=exc.code)
        except (ValueError, TypeError, KeyError):
            row.update(status="FAIL", reason="SMOKE_CHECK_FAILED_DETAILS_REDACTED")
        row.update(
            latency_ms=round((time.perf_counter() - started) * 1000),
            inference_requests=sum(bool(c.get("request_sent")) for c in calls),
            **{
                key: sum(c[key] for c in calls if type(c.get(key)) is int)
                if any(type(c.get(key)) is int for c in calls)
                else None
                for key in ("token_in", "token_out", "reasoning_tokens")
            },
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
