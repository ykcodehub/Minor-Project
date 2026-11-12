# Two-page risk agreement benchmark

Executed locally on 11 November 2026. All AI HTTP responses are mocked; no live model quality, actual billed usage, production latency or Render memory claim is made. Each case uses a temporary SQLite database, synthetic user, encrypted temporary filesystem storage, real extraction, worker, checkpoints, semantic-validation path, persistence and Summary API. The source is a generated two-page, 36-block agreement with seven known terms. The existing `synthetic_contract.pdf` is also checked for two-page mapping, but does not contain the new fixture's high-attention clauses.

| Adapter | State | Verified | Risk counts H/M/L | Candidate/index/semantic requests | Local wall seconds | Max estimated semantic input tokens | Retries |
|---|---|---|---|---|---|---|---|
| gemini (`gemini-3.6-flash`, mocked) | COMPLETED | 7/7 | 2/4/1 | 2/3/7 | 3.132 | 1126 | 0 |
| groq (`openai/gpt-oss-20b`, mocked) | COMPLETED | 7/7 | 2/4/1 | 5/3/7 | 2.263 | 1171 | 0 |
| openrouter (`test/structured:free`, synthetic model) | COMPLETED | 7/7 | 2/4/1 | 2/3/7 | 1.439 | 1193 | 0 |

Input figures use the application's full serialized-wire tokenizer estimate plus its existing safety margin; they are not authoritative provider token counts. Mock responses intentionally do not pretend to measure billed tokens or reasoning. Request-level estimated input, output reserves, payload bytes and local mock-handler time are retained in [two_page_risk_benchmark.json](two_page_risk_benchmark.json). Worker/API wall time includes local extraction, database and model-handler overhead; mock handler timings are not inference timings. These seven supported outcomes reflect the programmed fixture, not proof that a real model will recover every clause.

Reproduce from root: `.venv/Scripts/python.exe scripts/benchmark_risk_agreement.py`. The runner overrides database/provider settings in its child process and replaces only its synthetic JSON report. It never modifies `.env` or production records. All requests must fit existing provider/operation caps. PDF blocks remain separate and offsets unchanged; the viewer groups blocks by actual page and displays the original page total.

Regression tests separately simulate output consumed almost entirely by reasoning, prevent oversized output-growth retries and stop reasoning-only failures after the first confirmed exhausting response, independently per role including candidate generation. They also preserve ambiguous findings as Needs Review and withhold the priority index when coverage/verification/classification is incomplete. HTTP 400, outages, malformed output, consent, exhausted budgets and fallback are covered by the provider suites, not claimed as real successful inference. The current live preflight is BLOCKED, with zero inference requests; see [live_reliability_check.json](live_reliability_check.json).
