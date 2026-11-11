# AI operation reliability benchmark

Executed locally on 11 November 2026. These are isolated regression fixtures, not live inference, provider-quality tests or production timing measurements. HTTP responses are mocked; translation-cache cases mock the verified-batch service boundary. No paid calls, configured PostgreSQL records, SMTP or real identities are used.

| Operation | Local seconds | Observed result |
|---|---|---|
| quota_shared | 0.7306 | 3 synthetic HTTP calls: 1 primary 429, 2 authorized fallback successes across fresh operations; 90-second shared cooldown |
| translation_cache_hi | 0.5144 | 4 verified translations retained after failure; retry handles only remaining 3; no completed batch retranslated |
| translation_cache_hinglish | 0.489 | 4 verified translations retained after failure; retry handles only remaining 3; no completed batch retranslated |
| oversized_question | 0.2637 | 11 synthetic HTTP calls; 9 source sections, both selected sources audited, exact citation retained; max estimated semantic input 1106 tokens; max full request 11198 / 12000 tokens |

Raw records: [ai_operations.json](ai_operations.json). Timing includes local fixture setup/DB/API work and immediate synthetic responses, not actual model or provider network time. Authoritative token usage and billed cost are unmeasured. Input totals are the application's full serialized-wire estimate with existing safety margin and reserved output; a context window is not an accuracy guarantee.

Reproduce from root with `backend/.venv/Scripts/python.exe scripts/benchmark_ai_operations.py`. The runner replaces only its synthetic JSON report and forces temporary test database/provider settings in its child process. Existing 429/503/length/safety/400/malformed-response tests remain relevant regression evidence. [Two-page risk benchmark](TWO_PAGE_RISK.md) independently covers real PDF extraction, queue, worker, source indexing, exact quotes, persistence and risk Summary through all three mocked adapters.

Limits: shared cooldowns are reactive to observed 429 responses, not a provider quota oracle or a distributed request scheduler. Already in-flight concurrent requests cannot be recalled. Missing Retry-After/Google RetryInfo uses a conservative 60-second cooldown; actual daily/project quotas may take longer. Validated translation batches are stored on success or a handled provider failure; a process killed mid-request can still lose in-memory work. API chat and translation are synchronous operations, not new durable worker jobs. No live inference, Render load/memory or production PostgreSQL health claim is made.
