# Rate-limit recovery and demo checklist

Assessment date: **12 November 2026 (Asia/Calcutta)**. Verdict: **NOT READY for real-provider production acceptance**. The offline authored demo remains a tested backup. No new inference, production data write, credential change, commit, push or deployment was performed in this pass.

## What the recorded 429 establishes

The [previous controlled run](benchmarks/final_live_acceptance.json) requested `dots-studio/dots-3-note-preview:free`; successful responses identified AtlasCloud. Six requests succeeded, followed by HTTP 429 during semantic verification (75 ms). The complete run took 52.118 seconds and reserved an estimated 28,326 tokens across seven requests. Three completed semantic checkpoint verdicts were SUPPORTED; the run did not complete final findings, QA, translations or reports.

**The precise quota source is not recoverable from the retained evidence.** The live harness stopped at its outbound safety boundary before the adapter could retain Retry-After, quota headers or an error code. The report contains `DETAILS_REDACTED`, not a raw error body. It does not prove a daily quota, per-minute quota, billing restriction or AtlasCloud-specific limit. We have not invented a reset time or contacted providers to investigate further.

Future adapter diagnostics retain numeric Retry-After/typed retry delay, whether the delay came from the provider or the conservative default, allowlisted numeric quota headers and categorical quota scope. Raw messages, prompts, credential values and arbitrary header values remain excluded. Scope classification reflects provider prose, not independent verification of account quotas.

## Implemented recovery

1. Previously authorized fallback providers are tried according to existing user preference/task routing. No provider is added or authorized by recovery.
2. If fallback is exhausted with a rate-limit error, analysis stops at that boundary instead of repeatedly generating incomplete semantic checks.
3. With no uncertain RUNNING request, available persisted operation budget and remaining resume allowance, the job enters `WAITING_RATE_LIMIT`, stage `RATE_LIMIT_COOLDOWN`. Validated findings and completed request checkpoints remain stored. `lease_until` is a not-before timestamp for this waiting state, not an active worker lease.
4. The worker claims it only after that timestamp. Cooldown and resume counts survive process restarts in existing database fields. Each resumed operation rechecks current provider permission, source ownership/expiry, model compatibility and shared quota before inference. Completed requests are reused; only a definitively failed request can be sent again.
5. Unknown reset times wait at least 60 seconds, then at least 120 seconds on the second pause. Provider-requested delays are honored when longer. There are at most two automatic resumes and three total job attempts. Original persisted call/token budgets include failed requests and are never reset by resume.
6. Uncertain requests, exhausted budgets, explicit daily quota with no confirmed Retry-After, waits beyond the configured maximum, or exhausted resume limits stop automatic recovery. Results remain FAILED or PARTIAL_COMPLETION with an explicit stop reason. A worker crash with an uncertain remote request is never silently replayed.
7. Cancellation is supported while waiting. Summary remains Not Determinable while incomplete; retained findings keep their actual verification statuses. The UI shows the next eligible resume and reduces waiting polling to 15 seconds. Client polling still has a bounded pause. QA during processing/waiting returns 409; partial terminal results retain existing grounded-answer validation.

No database migration is needed: states are strings and scheduling metadata uses existing Job columns/JSON. This does not retroactively resume the old test's uncertain RUNNING checkpoint.

## Configuration to review before deployment

New optional settings (defaults already apply; `.env` was not modified):

```dotenv
AI_RATE_LIMIT_MAX_RESUMES=2
AI_RATE_LIMIT_MAX_WAIT_SECONDS=3600
```

Set `AI_RATE_LIMIT_MAX_RESUMES=0` to disable automatic recovery. Maximum is two. Long provider delays are not truncated to the configured wait. For a controlled demonstration, conservative **whole-job** caps can be set explicitly:

```dotenv
MAX_AI_CALLS_PER_OPERATION=20
MAX_AI_TOKENS_PER_OPERATION=80000
```

These are application caps, not a guarantee of provider quota or zero billing. Model pricing, endpoint availability, data policies and account-tier billing must be verified separately before approving inference.

Local safe configuration inspection found Gemini `gemini-3.6-flash`, Groq `openai/gpt-oss-20b` and OpenRouter `openrouter/free`; task-specific order is unset. **These local values do not establish Render's settings or healthy/free provider access.** The dynamic router is deliberately rejected for evidence-critical work. Replace it with an explicitly selected capability-validated model. The previously tested Dots ID is a candidate for requalification, not a production recommendation after its quota failure. No new model/provider or paid fallback was enabled.

`AI_TASK_PROVIDER_ORDER` remains optional JSON keyed by `candidate_generation`, `context_indexing`, `semantic_verification`, `question_answering`, etc. It reorders only providers already permitted by that user. Leave it unset until model/task compatibility and free-tier account access are verified; prioritizing a failing provider does not create quota.

## Exact deployment setup

Render Web Service, root `backend`:

```bash
pip install -r requirements.runtime.lock && pip install --no-deps -e .
python -m app.serve
```

The second line is the **Start Command**, running one API and one worker in the same service. Apply release migrations separately with `python -m app.manage migrate`; check drift with `python -m alembic check`. No migration was applied in this pass. Never reset the database to deploy this change.

Review Render configuration, keeping actual secrets in Render's environment settings:

```dotenv
ENVIRONMENT=production
PUBLIC_URL=https://veriora.vercel.app
ALLOWED_ORIGINS=https://veriora.vercel.app
GOOGLE_REDIRECT_URI=https://veriora.vercel.app/api/v1/auth/google/callback
OAUTH_PROXY_HOSTS=veriora-api.onrender.com
SECURE_COOKIES=true
SESSION_COOKIE_SAMESITE=lax
STORAGE_BACKEND=s3
S3_REGION=auto
```

Keep Neon `DATABASE_URL`, stable `STORAGE_KEY`, R2 `S3_BUCKET`/HTTPS `S3_ENDPOINT_URL`/AWS credentials, SMTP sender/configuration and OAuth credentials configured securely. Register the exact Google redirect URI above when using the same-origin Vercel proxy. Do not change cookie/state protections to work around deployment issues.

Vercel root `frontend`: install `npm ci`, build `npm run build`, output `dist`, `VITE_API_BASE_URL=/api/v1`. Existing `vercel.json` rewrites `/api/*` to `https://veriora-api.onrender.com/api/*` and serves SPA routes correctly. No Vercel setting was changed.

Render Free can sleep: a waiting job resumes only when the service is awake and the worker is running. This is durable recovery, not a scheduling/latency SLA. API `/ready` is not an AI quota check. Production deployed revision, settings and actual Google/SMTP/R2 behavior remain unverified.

## Short demonstration checklist

- Confirm the intended revision and `python -m app.serve` on Render; check API/worker readiness and migration head.
- Requalify explicit model/free endpoint/account quota and obtain approval before another bounded synthetic live test. No new inference was permitted in this pass.
- Use only the synthetic PDF; check actual PDF page count, supported/review finding counts, exact clickable quotations and incomplete coverage warnings.
- If rate limited, show next eligible resume; do not press retry repeatedly. Verify cached work is reused and the job eventually reaches a terminal state.
- Before claiming live readiness, complete Summary/dashboard, Detailed Analysis, grounded QA, Hindi/Hinglish and downloads against real responses.
- Keep `/demo/offline` open as the visibly labelled authored backup. Never call it fresh AI output.

Regression commands/results are in [VERIFICATION.md](VERIFICATION.md). Current read-only Neon evidence: [schema check](benchmarks/rate_limit_postgres_readonly.json). No new real-provider success or latency measurement is claimed.
