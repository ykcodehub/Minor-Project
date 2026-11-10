# Run and use Veriora

## Start locally

Use Python 3.12-3.13, Node 22.12+ or 24+, and reachable PostgreSQL. Preserve existing backend/.env. Install dependencies using the root README if needed; never copy an example over configured secrets.

From the project root, activate `.\.venv\Scripts\Activate.ps1`. Use three terminals:

```powershell
# Terminal 1: API
cd backend
python -m app.manage check
python -m app.manage migrate
python -m alembic check
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2: worker (same environment/database/storage key)
cd backend
python -m app.worker
```

```powershell
# Terminal 3: frontend
cd frontend
npm ci  # initial install or package-lock change
npm run dev
```

Open http://127.0.0.1:5173 . API docs: http://127.0.0.1:8000/docs ; health: http://127.0.0.1:8000/api/v1/health ; readiness: http://127.0.0.1:8000/api/v1/ready . Remote PostgreSQL needs no local Docker instance. Restart API/worker after Python changes. The worker performs queued processing and configured retention/deletion maintenance; review retention before running against valuable data.

## Use the application

1. Register with email only. Follow the verification link, then set/confirm a password. Login supports email/password and Google; forgot password sends a single-use reset link. Responses avoid exposing account existence.
2. Select the language through the global globe control. English, Hindi and Hinglish preferences persist for signed-in users.
3. Upload a supported document, paste text, or discover legal pages from a public website. Select accessible policies; discovery cannot guarantee exhaustive coverage.
4. In Settings, choose a preferred configured model and authorize permitted providers once. Start analysis using the saved permissions. The worker displays real stages; failures remain visible and can be retried safely.
5. Summary opens by default. Expand source/context for key clauses or select a source citation. Detailed Analysis contains filters, source navigation, Evidence Passport and Veriora AI; Processing Coverage is at its bottom.
6. Ask a document question or select a suggested question drawn from supported document categories. Quotes remain in their original language. Missing evidence produces an explicit abstention.
7. Download a report/manifest; use Library for history. Logout invalidates the current session.

Add your final image at frontend/public/logo.png. Missing/unreadable images use a text fallback. The global footer updates its year automatically.

## Troubleshooting

- Database failure: run `python -m app.manage check` from backend. Check reachability/TLS and credentials privately; runtime does not fall back to SQLite. Review migrations rather than resetting data.
- Import error `No module named app`: use the backend working directory and project virtual environment.
- Queued analysis: start the worker with the same database, storage key and provider configuration. Do not use fake progress or repeatedly enqueue duplicate analyses.
- Provider failure: inspect the safe error code, configured model and quota. An unavailable provider may fall back only to another provider already authorized in Settings. Review the actual failure codes and coverage.
- Google state/cookie error: start with the real Google button, allow full browser navigation and keep the configured callback host consistent. A localhost/127.0.0.1 change affects host-only cookies. Do not open/reuse callback URLs. Keep server time synchronized. State/nonce/PKCE and strict token expiry stay enabled.
- Email: privately verify SMTP authentication, sender ownership, delivery logs and spam folders. Accepted SMTP delivery is not proof of inbox receipt. No production OTP bypass exists.
- Upload/extraction: supported formats are PDF/DOCX/TXT/HTML. Scanned PDFs require OCR outside the current implementation; incomplete coverage is disclosed.
- S3: API and worker must share bucket/prefix/key and authorized IAM. Remote connectivity/conditional-write/retention must be tested on the chosen service before release. Never rotate STORAGE_KEY without a controlled data migration.
- Frontend API error: use the Vite proxy locally. Production uses a reviewed same-origin API rewrite and HTTPS; do not expose credentials in browser variables.

## Verification and deployment

Run the README's backend/frontend commands; `npm run build` includes TypeScript checks and `npm run test:e2e` starts isolated browser fixtures. Results and external-integration limitations are in [verification](docs/VERIFICATION.md).

Follow [deployment](docs/DEPLOYMENT.md) for Vercel frontend, separate API/worker hosting, fresh PostgreSQL, private object storage, Google and SMTP. Generate a reviewable Vercel configuration only after the real backend domain exists. No production deployment has been performed.

[Document cleanup](docs/DATABASE_RESET.md) defaults to a read-only plan. Destructive cleanup was not executed and requires a separate verified backup and explicit operator approval; production reset is prohibited.


Development proxy note: VITE_API_TARGET may be set in a frontend mode environment file or the process environment; process values take precedence. Restart Vite after changes. Preserve existing .env files. This cleanup pass performs no PostgreSQL changes; database cleanup remains a manual operator responsibility.


Authentication: email login now confirms /me before opening dashboard; logout/account deletion clear private caches and open sign-in. Browser OAuth failures redirect to a clean error page; do not reuse callback URLs. For Vercel/Render mobile sessions, use the first-party /api proxy and exact Google callback settings in docs/DEPLOYMENT.md. Direct cross-site None cookies require Secure and remain subject to browser privacy restrictions.


Single-service demo option: from backend run `python -m app.serve` instead of separate API/worker terminals. It binds PORT (default8000), supervises both processes, and exits if either child dies. On Render use root backend and Start Command python -m app.serve, with health path /api/v1/ready. Existing production security/Neon/R2/provider values stay in place. Do not run an additional worker unintentionally. If processing is interrupted, wait for lease recovery and use the existing explicit Retry action; status refresh does not rebill AI. See docs/DEPLOYMENT.md for free-tier limits.


Provider preferences: open Settings, select the primary configured model, check permitted providers and Save preferences. Future uploaded/pasted/discovered sources reuse these permissions; no repeated per-document consent checkbox is required. Uncheck providers and save to revoke them. Existing analyses, chat, translations and retries recheck current permissions. Uncheck all to stop further outbound AI requests. Guest trials still need analysis-scoped consent.

Before running this version against an existing database, apply `python -m alembic upgrade head` from backend through your authorized migration workflow. Do not start code requiring the new column against the old schema. No production data reset is required. Backend/worker start commands remain unchanged. On Render without Shell, arrange this additive migration in your approved startup/release workflow before the supervisor starts; do not skip it. Vercel needs a frontend rebuild, not new public secrets.

A partial Summary reports retained versus verified findings, source coverage and provider error codes. HTTP 413 is a context/request-size rejection. Configure PROVIDER_LIMITS to your model/plan budget if needed; see README. Small-context source-wide audits and retries share operation limits. No unverified candidate is promoted to fill an empty summary.

### OpenRouter router IDs and dense source maps

The 12,000-token OpenRouter default is an application request/output budget, not an asserted context length for `openrouter/free`. The router chooses an underlying model dynamically; returned `response_model` is retained for audit. Unknown selected-model context is not invented or cached as a fixed router capacity. An explicit configured `context_tokens` can only tighten the local cap; for a router it is labeled a configured router cap, not a guarantee about every selected model. Strict JSON/schema requirements remain enabled.

Candidate and context-audit chunks are now fitted against the same full serialized request estimate used immediately before HTTP: system/prompt, source IDs/offsets/pages/headings, JSON schema, tokenizer safety margin and reserved output. Dense metadata can exceed a budget even when the document text is short. The fitter divides original source spans and uses the existing sentence/token splitter for oversized individual spans. Every original character range remains accounted for. No source text is silently dropped; indivisible over-budget units fail explicitly and the 120-unit/operation guards remain in place. The application cap is not increased to make requests pass.

Model overrides now accept the exact configured model ID, such as `"openrouter/free"`, in PROVIDER_LIMITS. Precedence: provider defaults -> exact model ID -> namespaced `provider/model-id` override. The older `"openrouter/openrouter/free"` key remains supported. No environment change is required for the default router case. Do not set a guessed large context merely because the ID is a router. Tight plan/model limits may still require calibrated explicit budgets or a concrete supported model. Known upstream context-length rejections are classified separately from local preflight failures; raw provider error messages are never logged.

Fallback uses current saved permissions. Configuring Gemini/Groq keys does not authorize them; enable desired alternatives in Settings. An OpenRouter-only permission list correctly produces remaining_authorized=0. No new migration is required by this fix; the prior persistent-permissions migration must already be applied before running that application version.

References: https://openrouter.ai/docs/guides/routing/routers/free-router and https://openrouter.ai/docs/guides/overview/models . No live generation was used to verify the patch.

## 11 November 2026: shared source indexing and restart-safe analysis

The primary analysis path builds a source-wide, model-assisted qualification index once per source/provider and reuses it across findings. Every source window is scanned under the existing operation budgets; the old per-finding 12-window cutoff no longer gates analysis. A Unicode lexical index supplies target/neighbor passages and explicit cross-reference context, but retrieval alone never establishes support. All indexed quotations are checked against original source text/offsets/pages. Every material indexed excerpt is included in bounded semantic-review batches; support requires a complete source audit, resolved context and successful semantic review across all batches. Invalid/failed/unresolved audit output remains ambiguous/partial. The index is not independent legal proof; model omissions remain possible.

Wire requests use reversible request-local source/section aliases instead of repeated UUIDs. The server restores canonical identities before quote/ownership/offset checks or persistence. Unknown/mismatched references remain invalid. Exact wire guards still include schema/system/context/output allowances; no file/page/request/operation caps were raised. Semantic verification initially reserves 1,024 output tokens; source indexing 2,048; candidate generation retains the configured provider ceiling up to 4,096 initially. MAX_TOKENS/length output is discarded and may be regenerated with a bounded larger allowance only within provider/request limits; malformed/truncated JSON is never appended or accepted.

Durable job-scoped request checkpoints reserve estimated usage before network activity and store only validated completed responses. Retries reuse matching completed responses without another HTTP request, including a completed response obtained after a larger-output retry. Fingerprints include prompt/schema/model/task/version; source scope and current provider permission/lease checks remain enforced. Per-job durable call/token reservations survive restarts and explicit retries: retry does not reset spent budget. Interrupted requests with no saved response are uncertain, not assumed free/successful. The existing Retry action requires explicit acknowledgment before replaying such a request. No automatic paid replay occurs; completed source/model responses are reused. Source/account deletion cascades to checkpoints.

Apply the additive migration `python -m alembic upgrade head` from backend before starting the updated API/worker. New head: c819ba204ae1, adding analysis_checkpoints with job-delete cascade. It was tested only in a temporary database and compiled for PostgreSQL offline; Neon was not modified. No new environment variables, Redis, vector database or paid worker are required. Existing Render Start Command remains python -m app.serve after the authorized migration step.

The UI distinguishes completed per-provider source audits from each finding's semantic status, retains unsupported findings in Detailed Analysis and shows partial results/budget failures honestly. A recovered primary-provider audit failure does not invalidate a completed authorized fallback audit. An exhausted budget requires scope/usage review; repeatedly resuming cannot mint another operation budget.

Reproduce synthetic benchmarks with `backend/.venv/Scripts/python.exe scripts/benchmark_analysis.py` from repository root (or the equivalent activated interpreter). The script forces temporary SQLite/filesystem storage, synthetic users/documents and mocked provider HTTP. It measures PDF extraction, the real queue/worker, checkpoint/persistence path, exact citations, local elapsed time and one process's OS peak working set/RSS. See docs/benchmarks/analysis_benchmark.json and BENCHMARKS.md. These are not measurements of live API quality/latency/quotas or the combined Linux Render API+worker footprint. The fixture contains one known payment clause per page and a qualification every five pages; dense/ambiguous real contracts are not certified by passing it. Image-heavy/malformed 20 MiB documents and production concurrency still require separate memory/load qualification. All existing application and cost limits remain unchanged.
