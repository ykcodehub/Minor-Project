# Synthetic analysis benchmark ? 11 November 2026

Real generated PDFs, extraction, durable queue/worker, encrypted temporary storage, request checkpoints, findings persistence and strict evidence validation. All inference uses deterministic HTTP test doubles. No live provider or production database was contacted.

Fixture: about 558?562 extracted tokens/page, one known payment clause/page and an exception every five pages. A schema-valid synthetic evaluator supports a finding only when its expected exception is present. This tests orchestration and evidence plumbing, not legal-model quality.

Timing is measured local wall time from PDF creation through final persistence, excluding interpreter startup and real network/model latency. Peak is the OS-reported peak working set of one fresh Windows worker-equivalent process, including Python/native libraries; it is not a measurement of combined API+worker RAM on Linux Render. One run per matrix cell; no p95 or production SLA is inferred.

| Provider | Pages | State | Supported / retained | Exact citations | Index windows | Candidate units | Mock HTTP calls | Reserved tokens | Local seconds | Peak MiB |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gemini | 1 | COMPLETED | 1/1 | 1/1 | 0/0 | 1/1 | 2 | 9464 | 0.664 | 136.88 |
| gemini | 5 | COMPLETED | 5/5 | 5/5 | 3/3 | 2/2 | 10 | 46794 | 1.135 | 135.73 |
| gemini | 10 | COMPLETED | 10/10 | 10/10 | 5/5 | 4/4 | 19 | 93326 | 2.038 | 136.12 |
| gemini | 15 | COMPLETED | 15/15 | 15/15 | 8/8 | 5/5 | 28 | 140297 | 2.456 | 137.87 |
| gemini | 50 | PARTIAL_COMPLETION | 48/50 | 50/50 | 25/25 | 16/17 | 89 | 494881 | 7.753 | 140.64 |
| groq | 1 | COMPLETED | 1/1 | 1/1 | 0/0 | 1/1 | 2 | 7694 | 0.645 | 136.71 |
| groq | 5 | COMPLETED | 5/5 | 5/5 | 3/3 | 2/2 | 10 | 44670 | 1.182 | 135.97 |
| groq | 10 | COMPLETED | 10/10 | 10/10 | 5/5 | 4/4 | 19 | 87374 | 1.912 | 136.16 |
| groq | 15 | COMPLETED | 15/15 | 15/15 | 8/8 | 6/6 | 29 | 134974 | 2.652 | 137.63 |
| groq | 50 | COMPLETED | 50/50 | 50/50 | 25/25 | 18/18 | 93 | 494044 | 7.806 | 140.81 |
| openrouter | 1 | COMPLETED | 1/1 | 1/1 | 0/0 | 1/1 | 2 | 9762 | 0.633 | 136.44 |
| openrouter | 5 | COMPLETED | 5/5 | 5/5 | 3/3 | 2/2 | 10 | 48259 | 1.224 | 135.61 |
| openrouter | 10 | COMPLETED | 10/10 | 10/10 | 5/5 | 4/4 | 19 | 95546 | 1.843 | 135.86 |
| openrouter | 15 | COMPLETED | 15/15 | 15/15 | 8/8 | 5/5 | 28 | 143821 | 2.52 | 136.67 |
| openrouter | 50 | PARTIAL_COMPLETION | 47/50 | 50/50 | 25/25 | 16/17 | 88 | 495059 | 7.582 | 140.74 |

All source pages were extracted in every case. One-page cases use direct whole-source review and therefore need no index windows. All three adapters completed the 1/5/10/15-page fixtures with all expected interpretations supported by the synthetic evaluator and exact source citations. At 50 pages every adapter completed 25 source-index windows, exceeding the former per-finding 12-window restriction. Gemini/OpenRouter exhausted the unchanged estimated-token budget and correctly returned partial candidate/verification coverage; Groq completed this particular zero-error fixture near the same budget. Reserved tokens include conservative output allowances, not a measured dollar bill.

Do not generalize the 50-page result to dense contracts, malformed/image-heavy files or real free-tier quotas. More findings, retries, schema failures and model omissions can consume budgets sooner. The unchanged 100-call/500,000-reserved-token defaults remain enforced durably across retries. No application input/file/page/context limit was raised.

Reproduce: `backend/.venv/Scripts/python.exe scripts/benchmark_analysis.py` from repository root. The script asserts a temporary SQLite engine and substitutes all provider HTTP; it writes the machine-readable matrix alongside this report.
