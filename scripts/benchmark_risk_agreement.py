"""Repeatable synthetic risk/PDF benchmark. No configured DB, SMTP or AI is used."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / "docs/benchmarks/two_page_risk_benchmark.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[]\n", encoding="utf-8")
    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_URL": "sqlite://",
        "PYTHONPATH": str(ROOT / "backend"),
        "GEMINI_API_KEY": "",
        "GROQ_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "VERIORA_RISK_BENCHMARK_REPORT": str(target),
    }
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/test_risk_dashboard.py::test_two_page_agreement_to_verified_risk_summary",
            "-q",
            "--tb=short",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    for row in json.loads(target.read_text()):
        semantic = [c for c in row["requests"] if c["role"] == "semantic_verification"]
        print(
            json.dumps(
                {
                    "provider": row["provider"],
                    "mock_inference": True,
                    "state": row["state"],
                    "local_wall_seconds": row["wall_seconds"],
                    "max_estimated_semantic_input_tokens": max(
                        c["estimated_input_tokens"] for c in semantic
                    ),
                    "requests": len(row["requests"]),
                }
            )
        )


if __name__ == "__main__":
    main()
