# Final local readiness assessment — 12 November 2026

**Verdict: NOT READY for production/live-AI acceptance.** The clearly labelled offline college demo remains available as an authored reference, not fresh inference. No deployment, commit, production configuration change, or production database write was performed.

## Controlled real-provider run

The newly approved allowance was 20 requests / 80,000 estimated reserved tokens, synthetic data only, no retries or fallback. Fresh public metadata checks accepted explicit model `dots-studio/dots-3-note-preview:free`, structured-output capability, optional reasoning, a healthy endpoint and zero pricing. The provider was pinned with zero maximum prices. Only synthetic clauses were sent; no confidential documents or production accounts were used.

Actual execution: **7 requests, 28,326 estimated reserved tokens, 52.118 seconds**. Six HTTP 200 responses reported **7,408 input tokens, 1,224 completion tokens, zero reasoning tokens and zero cost** in total. The seventh request returned HTTP 429; it supplied no measured usage. Testing stopped immediately. The upstream quota period/cause is not established by the retained sanitized diagnostics.

| Stage | Actual result |
| --- | --- |
| Metadata/pricing/privacy gate | PASS for synthetic-only execution |
| Local registration/login | PASS with isolated test mail transport; no actual email delivery |
| PDF upload/extraction | PASS, six complete clauses on two original PDF pages |
| Source context indexing | PASS, one indexed/reviewed window; this is not semantic verification |
| Candidate generation | PASS, structured candidates returned |
| Semantic verification | BLOCKED after four completed verdicts: three SUPPORTED, one UNSUPPORTED |
| Final persisted analysis and evidence accuracy | BLOCKED; this recorded run persisted zero final findings |
| Summary / Risk Dashboard / Detailed Analysis live output | BLOCKED by incomplete analysis |
| Grounded QA, Hindi/Hinglish and report downloads | BLOCKED; not inferred from mocked tests |

The rejected license candidate used an incorrect RIGHT classification; rejection is preserved. Three supported checkpoint verdicts are real provider responses, **not a completed verified analysis or a document-wide accuracy score**. Exact synthetic quotations/pages and request-level outcomes are retained in [live evidence](benchmarks/final_live_acceptance.json) and [checkpoint review](benchmarks/final_live_checkpoint_review.json).

## Confirmed local fix after that run

Previously, findings were persisted only after the complete analysis returned. An interruption could leave completed semantic checkpoints but no retrievable findings. The worker now saves each validated finding incrementally, revalidates source ownership/quotation alignment, uses stable IDs for idempotent persistence, and retains conservative verification statuses. An interruption with retained findings produces PARTIAL_COMPLETION; no retained findings produces FAILED. Coverage remains explicitly incomplete until aggregation finishes. Existing request checkpoints allow an explicit retry without repeating completed inference requests.

This persistence fix was regression-tested locally, **not retested with live inference** after the 429 stop. It does not solve upstream quota exhaustion. No schema migration was introduced.

## Deployment preparation and external checks

- Render backend root: `backend`; build: `pip install -r requirements.runtime.lock && pip install --no-deps -e .`; start: `python -m app.serve`. The supervisor runs API and worker together. An isolated real supervisor smoke test reached readiness and consumed a queued ingestion job successfully.
- Apply migrations during the controlled release: `python -m app.manage migrate`. Check schema drift with `python -m alembic check`. These are deployment instructions, not claims of production execution in this pass.
- Vercel frontend: `npm ci`, `npm run build`, output `dist`; use the existing API rewrite and relative `VITE_API_BASE_URL=/api/v1`.
- Production requires `ENVIRONMENT=production`, Neon PostgreSQL, `STORAGE_BACKEND=s3`, stable encryption key, R2 endpoint/bucket/credentials, HTTPS public origin, correct allowed origin, secure cookies, SMTP and Google credentials. Keep secrets in hosting environment settings.
- With the same-origin Vercel proxy, use `PUBLIC_URL=https://veriora.vercel.app`, `ALLOWED_ORIGINS=https://veriora.vercel.app`, `GOOGLE_REDIRECT_URI=https://veriora.vercel.app/api/v1/auth/google/callback`, and the documented `OAUTH_PROXY_HOSTS=veriora-api.onrender.com`. Register that exact callback in Google Cloud. Preserve state/nonce protections.
- Local `OPENROUTER_MODEL=openrouter/free` remains unsuitable for evidence-critical operations. Configure an explicit capability-validated model instead. The tested Dots model is currently quota-blocked and is **not production-qualified** by this run. Do not assume changing the model ID resolves capacity. Keep only user-authorized providers enabled; no paid fallback was approved or used.
- Render deployed SHA/start command/settings remain unverified. `/ready` proves API/database/worker readiness, not provider quota or model health. Render Free sleep/restart and limited memory remain demo limitations.
- Read-only Neon inspection passed, schema head `c819ba204ae1` matched locally, no missing mapped tables. R2 live operations, real SMTP delivery, real Google consent and production browser authentication were not executed in this pass.

## Verification evidence

Frontend: 58 unit tests passed; ESLint, TypeScript and production Vite build passed. Browser: 32 passed, one intentionally skipped live-provider test. These use isolated synthetic/mocked services and do not establish remote AI reliability. Backend final results are recorded in [verification](VERIFICATION.md).

Additional evidence: [supervisor smoke](benchmarks/final_combined_service_smoke.json), [read-only PostgreSQL](benchmarks/final_postgres_readonly.json), [local configuration flags](benchmarks/final_configuration_audit.json). Local development configuration flags do not establish defects in Render's inaccessible environment.

## Release gate

Obtain stable zero-cost provider quota/capacity, then approve and execute a fresh bounded synthetic run through completed findings, exact citations, Summary/dashboard, QA, translations and downloads. Recheck actual SMTP/OAuth/R2 production integrations and deployed revision. Until those checks pass, use the clearly labelled offline backup for the college demonstration and do not claim production readiness.
