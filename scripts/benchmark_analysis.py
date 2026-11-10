"""Isolated synthetic PDF/worker benchmark. HTTP inference is always mocked, never live."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def peak_mb():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process = ctypes.WinDLL("psapi", use_last_error=True)
        process.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        if not process.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), ctypes.sizeof(counters)
        ):
            raise OSError("Memory measurement failed")
        return counters.PeakWorkingSetSize / 1024**2
    import resource

    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024**2 if sys.platform == "darwin" else 1024)


def child(pages, provider):
    temporary = Path(tempfile.mkdtemp(prefix="veriora-benchmark-"))
    os.environ.update(
        ENVIRONMENT="test",
        DATABASE_URL="sqlite:///" + (temporary / "test.db").as_posix(),
        STORAGE_BACKEND="filesystem",
        STORAGE_PATH=str(temporary / "objects"),
        GEMINI_API_KEY="",
        GROQ_API_KEY="",
        OPENROUTER_API_KEY="",
        VERIORA_WORKER_HEALTH_FILE=str(temporary / "health.json"),
    )
    sys.path.insert(0, str(ROOT / "backend"))
    import httpx
    import pymupdf
    from app.config import settings
    from app.db import Base, SessionLocal, engine
    from app.models import (
        Analysis,
        AnalysisCheckpoint,
        AnalysisSource,
        Finding,
        Job,
        Source,
        User,
        now,
    )
    from app.services.chunking import count_tokens
    from app.services.resources import create_source
    from app.worker import run_once
    from cryptography.fernet import Fernet
    from sqlalchemy import select

    assert engine.dialect.name == "sqlite"
    Base.metadata.create_all(engine)
    cfg = settings()
    cfg.environment = "development"
    cfg.storage_backend = "filesystem"
    cfg.storage_path = temporary / "objects"
    cfg.storage_key = Fernet.generate_key().decode()
    ids = {
        "gemini": "gemini-3.6-flash",
        "groq": "openai/gpt-oss-20b",
        "openrouter": "openrouter/free",
    }
    for name, model_id in ids.items():
        setattr(cfg, name + "_api_key", "synthetic" if name == provider else "")
        setattr(cfg, name + "_model", model_id)
    baseline = peak_mb()
    start = time.perf_counter()
    document = pymupdf.open()
    filler = "The agreement describes administrative procedures and record keeping for the service. "
    for number in range(1, pages + 1):
        first = f"Payment obligation for page {number}: The customer must pay invoices within thirty days subject to any stated exception. "
        paragraphs = [first + filler * 8]
        paragraphs.extend(
            f"Administrative section {number}.{i}. " + filler * 8 for i in range(1, 5)
        )
        if number % 5 == 0:
            paragraphs.append(
                f"Exception clause for page {number}: Payment is paused while a written invoice dispute is investigated."
            )
        page = document.new_page()
        remaining = page.insert_textbox(
            pymupdf.Rect(30, 30, 565, 810), "\n\n".join(paragraphs), fontsize=8
        )
        assert remaining >= 0
    raw = document.tobytes()
    document.close()
    requests = []
    original = httpx.Client

    def respond(request):
        assert request.url.host in {
            "generativelanguage.googleapis.com",
            "api.groq.com",
            "openrouter.ai",
        }
        payload = json.loads(request.content)
        prompt = (
            payload["contents"][0]["parts"][0]["text"]
            if provider == "gemini"
            else payload["messages"][1]["content"]
        )
        if prompt.startswith("Extract"):
            passages = json.loads(prompt[prompt.index("[") :])
            findings = []
            for passage in passages:
                text = passage["text"]
                if not text.startswith("Payment obligation for page "):
                    continue
                quote = text[: text.index(".") + 1]
                findings.append(
                    {
                        "source_id": passage["source_id"],
                        "section_id": passage["section_id"],
                        "page": passage["page"],
                        "quote": quote,
                        "start": passage["start_offset"],
                        "end": passage["start_offset"] + len(quote),
                        "category": "OBLIGATION",
                        "statement": quote,
                        "rationale": "Synthetic fixture: the supplied sentence states this obligation with its exception qualification.",
                        "qualifications": ["Subject to any stated exception."],
                        "cross_references": [],
                    }
                )
            output = {"findings": findings[:6]}
            role = "generation"
        elif prompt.startswith("Index every"):
            passages = json.loads(prompt[prompt.index("[") :])
            relevant = []
            for passage in passages:
                text = passage["text"]
                pos = text.find("Exception clause for page ")
                if pos < 0 or "." not in text[pos:]:
                    continue
                quote = text[pos : text.index(".", pos) + 1]
                relevant.append(
                    {
                        "source_id": passage["source_id"],
                        "section_id": passage["section_id"],
                        "page": passage["page"],
                        "quote": quote,
                        "start": passage["start_offset"] + pos,
                        "end": passage["start_offset"] + pos + len(quote),
                    }
                )
            output = {"relevant_passages": relevant, "unresolved_context": False}
            role = "index"
        elif prompt.startswith("Review this candidate"):
            data = json.loads(prompt[prompt.index("{") :])
            number = data["candidate"]["page"]
            has_exception = number % 5 != 0 or any(
                f"Exception clause for page {number}:" in p.get("text", "")
                for p in data["context"]
            )
            output = {
                "support_status": "SUPPORTED" if has_exception else "AMBIGUOUS",
                "rationale": "Synthetic rule evaluation, not a model-quality judgment.",
                "missing_qualifiers": [],
                "unresolved_references": []
                if has_exception
                else ["Missing synthetic exception."],
            }
            role = "verification"
        else:
            raise AssertionError("Unexpected task in isolated benchmark")
        result = json.dumps(output)
        requests.append(role)
        if provider == "gemini":
            return httpx.Response(
                200,
                json={
                    "modelVersion": "synthetic-gemini",
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": result}]},
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": count_tokens(prompt),
                        "candidatesTokenCount": count_tokens(result),
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "model": "synthetic-selected-model",
                "choices": [{"finish_reason": "stop", "message": {"content": result}}],
                "usage": {
                    "prompt_tokens": count_tokens(prompt),
                    "completion_tokens": count_tokens(result),
                },
            },
        )

    httpx.Client = lambda **kw: original(transport=httpx.MockTransport(respond), **kw)
    with SessionLocal() as db:
        user = User(
            is_guest=False,
            verified_at=now(),
            preferred_provider=provider,
            authorized_providers=[provider],
        )
        db.add(user)
        db.flush()
        source, _ingest = create_source(db, user, raw, "Synthetic.pdf")
        db.commit()
        owner = user.id
        sid = source.id
    assert run_once()
    with SessionLocal() as db:
        source = db.get(Source, sid)
        if source.status not in ("READY", "PARTIAL"):
            raise RuntimeError("Synthetic extraction failed")
        text_tokens = source.details["token_count"]
        page_coverage = source.details["coverage"]
        job = Job(
            owner_id=owner,
            kind="analysis",
            payload={
                "source_ids": [sid],
                "provider": provider,
                "consent": True,
                "fallback_providers": [],
                "privacy_mode": "external",
            },
        )
        db.add(job)
        db.flush()
        record = Analysis(owner_id=owner, job_id=job.id)
        db.add(record)
        db.flush()
        db.add(AnalysisSource(analysis_id=record.id, source_id=sid))
        db.commit()
        jid = job.id
        aid = record.id
    assert run_once()
    with SessionLocal() as db:
        job = db.get(Job, jid)
        record = db.get(Analysis, aid)
        findings = [
            f.data
            for f in db.scalars(select(Finding).where(Finding.analysis_id == aid))
        ]
        checkpoints = db.scalars(
            select(AnalysisCheckpoint).where(AnalysisCheckpoint.job_id == jid)
        ).all()
        indexes = record.coverage.get("context_indexes", [])
        result = {
            "pages": pages,
            "provider": provider,
            "configured_model": ids[provider],
            "mock_inference": True,
            "state": job.state,
            "document_tokens": text_tokens,
            "extracted_pages": page_coverage["pages_extracted"],
            "findings": len(findings),
            "supported": sum(f["support_status"] == "SUPPORTED" for f in findings),
            "exact_citations": sum(
                c["match_status"] == "EXACT" for f in findings for c in f["citations"]
            ),
            "candidate_chunks_total": record.coverage.get("chunks_total", 0),
            "candidate_chunks_processed": record.coverage.get("chunks_processed", 0),
            "index_windows_total": sum(i["windows_total"] for i in indexes),
            "index_windows_processed": sum(i["windows_processed"] for i in indexes),
            "http_requests": len(requests),
            "reserved_tokens": sum(c.reserved_tokens for c in checkpoints),
            "wall_seconds": round(time.perf_counter() - start, 3),
            "baseline_peak_mib": round(baseline, 2),
            "peak_worker_process_mib": round(peak_mb(), 2),
        }
    engine.dispose()
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--provider", default="gemini")
    args = parser.parse_args()
    if args.child:
        child(args.pages, args.provider)
        return
    rows = []
    for provider in ("gemini", "groq", "openrouter"):
        for pages in (1, 5, 10, 15, 50):
            completed = subprocess.run(
                [
                    sys.executable,
                    __file__,
                    "--child",
                    "--provider",
                    provider,
                    "--pages",
                    str(pages),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if completed.returncode:
                raise RuntimeError(
                    f"Isolated benchmark failed: {provider}/{pages}: "
                    + completed.stderr[-2500:]
                )
            row = json.loads(completed.stdout.splitlines()[-1])
            rows.append(row)
            print(json.dumps(row), flush=True)
    target = ROOT / "docs" / "benchmarks"
    target.mkdir(exist_ok=True)
    (target / "analysis_benchmark.json").write_text(
        json.dumps(
            {
                "date": "2026-11-11",
                "platform": sys.platform,
                "scope": "Synthetic PDF extraction, real queue/worker/checkpoints/persistence; mocked HTTP inference. Single worker-equivalent process peak, not combined Render deployment.",
                "rows": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
