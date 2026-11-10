# Veriora 2.0

Veriora explains legal documents using checkable source evidence. Findings describe captured document text, not a company's actual conduct, legal enforceability or court admissibility.

## Implemented workflows

- Email-first verified registration, password reset, Google OpenID Connect, secure sessions and per-user authorization.
- PDF, DOCX, TXT and HTML uploads; pasted text; SSRF-protected legal-page discovery with explicit coverage limitations.
- Section/paragraph/token-aware chunking with original offsets and page references where extraction provides them.
- Gemini, Groq and OpenRouter adapters with selected-model routing, structured validation and separate source/semantic review.
- PostgreSQL jobs, real progress, cancellation/retry, analysis history, grounded questions, evidence navigation and reports.
- Summary opens first; Detailed Analysis preserves findings, source viewer and chat. Technical coverage appears at the bottom of Detailed Analysis. Quotes/context expand on demand.
- Global English, Hindi and Hinglish preferences; original quotations remain unchanged. Suggested questions use supported categories present in the document.
- Private encrypted storage: filesystem for development, S3-compatible object storage required in production. Remote S3 qualification remains pending.

See [requirement status](docs/REQUIREMENTS_AUDIT.md), [verification evidence](docs/VERIFICATION.md), and [step-by-step usage](HOW_TO_RUN.md). Production readiness is not claimed.

## Architecture and repository

React 19 / TypeScript / Vite / TanStack Query / Lucide; Python 3.12-3.13 / FastAPI / SQLAlchemy / Alembic / PostgreSQL 16+. Extraction uses PyMuPDF, python-docx and BeautifulSoup; chunk sizing uses tiktoken. No Redis or vector database is required.

```text
frontend/src/         application, workspace, shared UI and localization
frontend/e2e/         browser regressions
backend/app/          HTTP API, security, providers, services and worker
backend/migrations/   versioned PostgreSQL schema
backend/tests/        unit, API, security and evidence regressions
scripts/              local verification and deployment configuration tools
docs/                 specifications, audit, verification and operations
```

Browser -> API -> PostgreSQL and encrypted storage. A separately supervised worker consumes durable jobs, extracts/chunks text, calls the selected provider, verifies evidence and persists results. Reports and questions reuse authorization and evidence services. Optional private read-only MCP is available; public MCP OAuth is planned.

## Local setup

Requires Python 3.12-3.13, Node 22.12+ or 24+, and PostgreSQL. Run from the repository root in PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.lock
python -m pip install --no-deps -e backend
cd frontend
npm ci
cd ../backend
# Configure backend/.env privately ONLY if it does not already exist.
python -m app.manage check
python -m app.manage migrate
python -m alembic check
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In separate activated terminals, run `python -m app.worker` from backend and `npm run dev` from frontend. UI: http://127.0.0.1:5173 ; API docs: http://127.0.0.1:8000/docs . The development proxy forwards /api; keep Google login on its configured canonical hostname.

For a new database, create a PostgreSQL role/database you control and configure DATABASE_URL privately. Existing configured remote PostgreSQL needs no local Docker database. Migrations preserve existing records; do not downgrade/reset to fix errors. Never overwrite an existing .env.

## Configuration

[backend/.env.example](backend/.env.example) contains placeholders only. DATABASE_URL selects PostgreSQL/psycopg; ENVIRONMENT, SECURE_COOKIES, PUBLIC_URL and ALLOWED_ORIGINS control runtime security. STORAGE_KEY must remain stable; STORAGE_PATH is development-only. STORAGE_BACKEND, S3_BUCKET, S3_REGION, S3_ENDPOINT_URL and S3_PREFIX select private production objects; AWS SDK credentials come from host secrets/IAM. MAX_UPLOAD_BYTES, MAX_PAGES and MAX_DOCUMENT_TOKENS bound ingestion. Each provider uses its *_API_KEY and *_MODEL; the user's selected provider is preserved. SMTP_HOST/PORT/USER/PASSWORD and MAIL_FROM enable real email; GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI enable Google. OAUTH_PROXY_HOSTS explicitly allowlists the production HTTPS backend ingress behind a same-origin rewrite. Never expose secrets through VITE_* variables.

## Tests

```powershell
cd backend
python -m pytest tests -q
python -m ruff check app tests
python -m alembic check
cd ../frontend
npm run lint
npm test
npm run build
npm run test:e2e
```

Build includes TypeScript checks. The browser harness uses isolated data and synthetic external-provider boundaries; it does not prove production Google, SMTP or AI service availability. See verification for executed counts and skips.

## Branding and deployment

Place the final logo at frontend/public/logo.png. Until supplied, a safe text mark appears. The footer uses the current year.

Deploy the frontend to Vercel and API/worker to persistent Python/container hosting, with a fresh PostgreSQL database and private S3-compatible bucket. [Deployment instructions](docs/DEPLOYMENT.md) cover generated API/SPA rewrites, Docker, storage, OAuth, SMTP and release gates. No infrastructure was deployed. [Database cleanup](docs/DATABASE_RESET.md) is read-only by default, requires separate approval/backup for development or staging, and refuses production deletion.

## Security, limitations and contribution

Preserve .env, encryption keys, private documents and database backups outside Git. Encrypted storage does not remove provider privacy obligations: review consent and retention before sending documents. Source quotation checks and model review cannot guarantee legal correctness. OCR, human reviewer sign-off, trusted timestamps, semantic comparison alerts and public MCP OAuth remain planned. Production S3/IAM, domain-specific OAuth/SMTP, container hosting, backup/restore and load qualification remain release gates.

Use small changes, preserve existing contracts and migrations, run the relevant regression suite and update the requirement audit. Never commit credentials, reset user data or claim unexecuted tests passed.


## Configuration and cleanup boundaries

The brand wordmark has no trailing dot. Navigation includes visible hover/active/focus states and respects reduced motion. Summary guidance expands on demand; Veriora AI uses a neutral localized input prompt and document-derived suggestions. Citation page labels use the global language catalog.

Development proxy overrides can be supplied through frontend environment files or VITE_API_TARGET in the process environment (process values win); restart Vite after changes. Production public/CORS origins must be HTTPS origins without credentials, paths or query strings. Loopback production database, object-store and configured Google callback hosts are rejected. Provider API URLs, allowed Google issuers, supported languages, risk rules and test fixtures are intentional constants rather than fabricated application results.

Do not delete dependencies, diagnostic scripts, specifications or tests merely because they are absent from the browser bundle. Runtime/test/build tooling have separate uses; generated files and private data are ignored/excluded from deployment artifacts. See the latest requirements audit and verification record for cleanup scope. No PostgreSQL modifications are part of the cleanup audit.


Authentication deployment: frontend/vercel.json now targets the supplied Render backend and includes SPA fallbacks. Use VITE_API_BASE_URL=/api/v1 with the first-party proxy and align PUBLIC_URL/Google callback with the Vercel origin; see the latest authentication section in docs/DEPLOYMENT.md. SESSION_COOKIE_SAMESITE defaults to lax; optional none requires Secure and does not bypass browser third-party-cookie blocking. No deployment has been performed.
