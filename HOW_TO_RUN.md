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
