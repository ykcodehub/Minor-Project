"""Synthetic quota, cached-translation and bounded-question benchmark; never production."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    report = ROOT / "docs/benchmarks/ai_operations.json"
    report.write_text("[]\n")
    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_URL": "sqlite://",
        "PYTHONPATH": str(ROOT / "backend"),
        "GEMINI_API_KEY": "",
        "GROQ_API_KEY": "",
        "OPENROUTER_API_KEY": "",
        "VERIORA_OPERATION_BENCHMARK_REPORT": str(report),
    }
    selected = [
        "test_429_shared_across_roles_and_fresh_operations_only_authorized_fallback",
        "test_partial_verified_translation_is_persisted_and_resumed_without_rebilling",
        "test_oversized_qa_uses_bounded_generation_and_audits_uncited_sources",
    ]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *["backend/tests/test_ai_operations.py::" + name for name in selected],
            "-q",
            "--tb=short",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    for row in json.loads(report.read_text()):
        print(json.dumps(row))


if __name__ == "__main__":
    main()
