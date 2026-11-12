# Explicit-model reliability policy

Implemented locally on 11 November 2026; not deployed. These changes contain provider failures rather than guarantee upstream availability or legal accuracy.

## Model selection and consent

Keep the existing `GEMINI_MODEL`, `GROQ_MODEL`, `OPENROUTER_MODEL` and user provider permissions. The preferred authorized provider still runs first. Fallback uses only the already-authorized list; a task-specific reasoning failure suppresses that provider/role for the current operation, without suppressing unrelated roles or granting permissions.

**Required operator change if using a router:** replace `OPENROUTER_MODEL=openrouter/free` or `openrouter/auto` with an explicitly selected model ID. No model replacement, paid model, credential change or production configuration change was made here. Select a concrete model only after reviewing its privacy terms, current price and real task results. A `:free` suffix alone is not accepted as proof of zero price by the smoke runner.

OpenRouter's public model catalog is consulted before sending document text. Its structured-output/max-token capabilities and actual context/output caps must match the request. Results are cached for five minutes; catalog outages are cached for 30 seconds and fail closed. Model removal or metadata changes can require reselection; API readiness does not certify provider availability. Metadata compatibility is not evidence of successful inference.

## Reasoning and budgets

- Optional OpenRouter reasoning is explicitly disabled where the model advertises that control. `exclude=true` is no longer treated as disabling reasoning.
- Mandatory-reasoning OpenRouter models are rejected before inference under the compact structured-output policy. A rejected reasoning-disable parameter never causes a retry with reasoning enabled.
- Gemini controls are applied only to recognized model IDs: low thinking for the listed Gemini 3 Flash models; zero thinking budget for supported Gemini 2.5 Flash variants. Existing Groq GPT-OSS low-effort settings remain.
- Complete serialized input, system/schema/policy overhead and reserved completion tokens remain subject to application and model caps. Catalog caps can only tighten limits. Growth cannot repeatedly request a completion allowance above the model maximum.
- A truncated response whose reported reasoning consumes at least 90% of the reserved allowance becomes `PROVIDER_REASONING_EXHAUSTED`. It is rejected, not repaired or promoted to supported evidence. It does not trigger compact retries or recursive candidate splitting; authorized fallback may still succeed.
- Truncation without evidence of reasoning exhaustion retains the existing bounded changed-request recovery and honest partial coverage.

## Outages and diagnostics

Exhausted temporary failures/timeouts create a separate hashed `ai-outage:` rate bucket, normally 30 seconds. A longer upstream Retry-After is respected. It is shared by processes using the same database and isolated from existing 429 quota buckets. Existing jitter/backoff and per-operation limits remain; a subsequent request can try again after expiry. Completed checkpoints can be reused during a cooldown without a new reservation.

Logs distinguish candidate generation, indexing, semantic verification, translation and QA by operation and role, with bounded model/status/usage metadata. Worker analysis attempts also include sanitized job and analysis IDs. Index progress uses `AI_CONTEXT_INDEXING`; a partial job's final stage is `PARTIAL_COMPLETION`. `remaining_candidates` describes only the supplied fallback list, not all globally authorized or healthy providers.

Exact quotes, offsets, PDF pages, qualification auditing, translation caches, Risk Dashboard and strict verification are preserved. A failed index is not a verified source, a partial analysis is not safe, and a service outage is not an unsupported document answer.

## Safe real-provider verification

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/check_ai_reliability.py --allow-provider openrouter --report docs/benchmarks/live_reliability_check.json
```

The runner reads existing configuration privately but never imports the database/session services, creates accounts, uploads files or writes production records. It requires an already-configured explicit `:free` model, catalog-confirmed zero prompt/completion prices, capability validation and explicit synthetic-test consent. It does not substitute a model. Limits: four inference attempts, 16,000 estimated reserved tokens, at most 2,048 completion tokens per request, zero retries and a 90-second operation deadline checked before attempts. Individual in-flight HTTP requests retain their bounded transport timeout; the deadline is not a guarantee of wall-clock duration. Input is one synthetic payment/dispute clause, not a live-user document.

Gemini/Groq inference remains blocked by this runner because free-tier billing cannot be established safely from a credential alone. Use a separately approved zero-spend project/provider policy before live testing them. This does not disable these configured providers in the application.

Results distinguish blocked checks, failed inference, partial and completed analysis. Actual returned token usage is recorded only when available. A successful run with zero supported findings is not proof of evidence quality; inspect verified counts and coverage. The current check was BLOCKED for all configured providers, with zero inference requests; see the JSON report and [verification](VERIFICATION.md). No real-provider latency or accuracy claim is made.
