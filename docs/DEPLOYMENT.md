# Production deployment preparation

No production deployment or infrastructure modification was performed. The app uses a Vite frontend, persistent FastAPI API, dedicated worker, PostgreSQL and private object storage. Vercel alone does not host this whole architecture.

## Architecture

```text
Browser -> Vercel static frontend
           /api/* same-origin rewrite -> HTTPS FastAPI service
                                        PostgreSQL (durable jobs/provenance)
                                        Private S3-compatible bucket (encrypted objects)
Dedicated persistent worker ----------> same database/bucket/encryption key
```

Use a suitable container/VM/Python host for API and worker. The backend Dockerfile runs Python3.13 as a non-root user with a pinned49-distribution runtime lock; tests, tools, local .env, runtime documents and caches are excluded by the Docker allowlist. Worker command: `python -m app.worker`. API command: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`. Adjust the host's port configuration. Container build/runtime and remote services still require staging validation.

## Vercel frontend

1. Obtain the actual public HTTPS backend origin. No backend URL or cloud resource is invented here.
2. From root generate a reviewable configuration: `python scripts/prepare_vercel.py --api-origin https://YOUR-REAL-BACKEND-HOST`. This writes frontend/vercel.json without deploying. A clearly non-deployable template is frontend/vercel.example.json.
3. Review the API rewrite before the SPA fallback and security headers. Set Vercel project root to `frontend`, framework Vite, build `npm run build`, output `dist`.
4. Keep VITE_API_BASE_URL unset or `/api/v1` for same-origin cookies. Do not place credentials in VITE_* variables. Avoid unrelated frontend/backend cookie domains that depend on third-party cookies.
5. Register the final app domain and verify `/analysis/:id`, `/dashboard`, `/sign-in` direct navigation, API errors, logo fallback and downloads in staging. External rewrites have platform request/body/time limits: qualify upload size and long synchronous chat/translation/report calls against your Vercel plan before release; long document analysis runs on the worker, not a Vercel function.

References: [Vercel external rewrites](https://vercel.com/docs/routing/rewrites), [vercel.json routing](https://vercel.com/docs/project-configuration/vercel-json). Deployment configuration is prepared, not remotely verified.

## Backend, database and storage

- Provision a **fresh PostgreSQL production database** and restricted runtime role. Preserve existing local/dev data. Supply DATABASE_URL through secret management; run `python -m app.manage migrate` and `python -m alembic check` as a release step. No startup reset or automatic downgrade.
- Set ENVIRONMENT=production, SECURE_COOKIES=true, a stable STORAGE_KEY, STORAGE_BACKEND=s3, S3_BUCKET, S3_REGION and optionally an HTTPS S3_ENDPOINT_URL/S3_PREFIX. Filesystem storage and test mail transports are rejected in production. API and worker share bucket/prefix/key; .env is never baked into the image.
- Supply S3 credentials through host process secrets or IAM roles using the standard AWS SDK chain. Grant only required GetObject/PutObject/DeleteObject access to the private application prefix; block public access. The adapter encrypts bytes with the existing Fernet key, requests AES256 storage encryption for AWS-style endpoints (R2 uses automatic at-rest encryption) and uses conditional PUT to prevent overwrite, validates object identifiers and bounds reads. The selected S3-compatible service must support these operations. SDK-mocked roundtrip/failure tests pass; a real bucket/IAM/lifecycle smoke test remains required.
- Keep uploads out of Vercel/public directories. No local persisted file dependency is required by the production S3 adapter. Existing local originals are not automatically moved; a controlled migration/backup is needed if they must be imported. Unknown objects are never swept.
- Back up PostgreSQL, private objects and encryption keys separately. Validate restore. Configure object-version/noncurrent-version expiry to match disclosed retention; delete markers are not proof of physical erasure of older versions.
- Health: `/api/v1/health`; database readiness `/api/v1/ready`. Supervise the worker, monitor queue age, leases, provider limits, deletion backlog, object capacity and failures. These operational alerts are deployment responsibilities.

## OAuth, SMTP, proxy and CORS

Set PUBLIC_URL and ALLOWED_ORIGINS to the final HTTPS app origin. Configure the exact Google Web-client redirect `https://APP-HOST/api/v1/auth/google/callback` (through the Vercel rewrite). Set OAUTH_PROXY_HOSTS to the explicit HTTPS backend ingress hostname accepted behind the rewrite. This avoids a canonical-origin redirect loop without trusting arbitrary X-Forwarded-Host. Use trusted proxy headers/allowed proxy addresses at the API host; do not globally trust client-supplied forwarding headers. Local loopback aliases remain canonicalized as before.

Configure Google client credentials and production SMTP sender/delivery privately. Recheck sender/domain ownership, SPF/DKIM/DMARC and actual mailbox receipt. Cookies stay host-only/HttpOnly/SameSite=Lax/Secure. Google state/nonce/PKCE/signature/audience and strict expiration remain active. A bounded30-second issuer-clock allowance is not a substitute for synchronized server clocks. User-confirmed local Google login passed; production-domain consent/callback must be tested separately.

The API also enforces Origin/CSRF checks. Expose only the API listener through HTTPS, apply proxy body/read deadlines and rate limits, and isolate parsing with non-root privileges and CPU/memory constraints. Ensure the platform does not log OAuth query strings or document bodies. Frontend CSP allows local built scripts, styles and images; evaluate any future assets before expanding it.

## Release gates still open

Actual backend/app domains; remote S3 credentials, conditional writes and retention; production OAuth/SMTP; container build and host qualification; Vercel proxy upload/time limits; backup/restore; two-worker load/cancellation; independent security/accessibility/linguistic and human evidence benchmark review. OCR/reviewer sign-off/semantic conflict alerts/trusted timestamps/public MCP OAuth remain planned features, not deployed functionality. See REQUIREMENTS_AUDIT.md and VERIFICATION.md.


Configuration audit: production rejects loopback database/object-store/configured Google callback hosts; public/CORS values must be HTTPS origins without URL credentials, paths or query strings. The Vercel configuration generator rejects loopback IP variants and .localhost names. Development defaults and test/CI fixtures are intentional; no production model IDs, credentials or fabricated findings are baked into frontend assets.


## Render + Neon + Cloudflare R2: startup configuration

No Render push/deploy or remote database/bucket modification was performed. Production validation remains strict; there is no temporary filesystem/testing bypass. Configure API and worker environment variables through the hosting secret manager, not a committed .env:

```text
ENVIRONMENT=production
STORAGE_BACKEND=s3
S3_BUCKET=<private R2 bucket name>
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_REGION=auto
SECURE_COOKIES=true
PUBLIC_URL=https://<actual frontend host>
ALLOWED_ORIGINS=https://<actual frontend host>
```

Keep the existing DATABASE_URL pointing to Neon with the required TLS settings, and the existing stable STORAGE_KEY. Supply R2's S3 access credentials as AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY through Render process environment variables (the SDK credential chain does not read Pydantic's local .env). Keep the bucket private; use the S3 API endpoint, not an r2.dev public object URL or a bucket-suffixed URL. Keep TEST_MAIL_OUTBOX unset. If Google is configured, set the exact public HTTPS GOOGLE_REDIRECT_URI and authorized Google client callback; do not retain localhost. Configure OAUTH_PROXY_HOSTS only for your explicit trusted backend ingress when using the same-origin rewrite.

Use the backend root directory, install the runtime lock and package as documented, and run `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT` on Render. Health-check path: /api/v1/health. Do not automatically reset data or run destructive migrations on startup. A reliable separately hosted worker is still required for analysis; do not claim a free sleeping web service provides it.

A startup failure now logs a static policy code with relevant variable names, never configured values. PRODUCTION_STORAGE_REQUIRED identifies filesystem storage or test-mail capture; S3_CONFIGURATION_REQUIRED identifies missing bucket/key; PUBLIC_ORIGINS_INVALID identifies public/CORS defaults or invalid origin forms; GOOGLE_REDIRECT_INVALID identifies an invalid callback; S3_HTTPS_REQUIRED/S3_PREFIX_INVALID/PRODUCTION_ENDPOINT_INVALID/POSTGRES_DRIVER_REQUIRED identify their named settings. Correct the indicated Render environment values and redeploy manually. The old generic database_policy message could not identify which rule failed and was not evidence of a Neon connectivity failure.

The R2 adapter omits the unsupported AWS SSE-S3 upload header for official R2 endpoint hosts only. Existing application-layer encryption, integrity hashing, TLS and conditional no-overwrite PUT are preserved. AWS/other S3 endpoints retain the AES256 header. R2 automatically encrypts objects at rest. References: [R2 compatibility](https://developers.cloudflare.com/r2/api/s3/api/), [R2 encryption](https://developers.cloudflare.com/r2/reference/data-security/). Remote credentials, bucket permission and real Render/R2 operation still require validation in your environment.


## Authentication deployment fix: first-party proxy (latest)

The prepared frontend/vercel.json routes /api/* to https://veriora-api.onrender.com/api/* before the SPA fallback. The backend remains reachable at its published API base; the browser should use the same-origin proxy for reliable mobile sessions.

### Required manual configuration

Vercel project root: frontend. Set VITE_API_BASE_URL=/api/v1 (replace a direct Render URL), then rebuild/redeploy manually with the prepared vercel.json. This also fixes direct /sign-in, verification/reset and dashboard links. Its CSP intentionally allows same-origin API connections; leaving a direct API URL while adopting that CSP will block requests.

Render API/worker retain the existing Neon/R2/secrets configuration. Set these public/security settings:

```text
ENVIRONMENT=production
SECURE_COOKIES=true
SESSION_COOKIE_SAMESITE=lax
PUBLIC_URL=https://veriora.vercel.app
ALLOWED_ORIGINS=https://veriora.vercel.app
GOOGLE_REDIRECT_URI=https://veriora.vercel.app/api/v1/auth/google/callback
OAUTH_PROXY_HOSTS=veriora-api.onrender.com
```

Google Cloud Web OAuth client: add the exact authorized redirect URI https://veriora.vercel.app/api/v1/auth/google/callback and the frontend origin https://veriora.vercel.app where an authorized JavaScript origin is requested. Retain other deliberately supported URIs as needed; the configured callback above must match exactly. Keep client secret server-side. Verify consent-screen/test-user permissions separately. Do not paste callback URLs/codes/tokens into diagnostics.

Both OAuth start and callback must pass through the Vercel /api rewrite so host-only cookies belong to the frontend origin. Google button uses full browser navigation, never fetch for the authorization entry. State, nonce, PKCE, signature, audience, strict expiry and single-use database state stay enabled. OAuth transient cookie remains HttpOnly/Secure/SameSite=Lax on its auth path, suitable for Google's top-level GET callback. Session cookies remain host-only, HttpOnly and Secure; no Domain can share cookies between unrelated vercel.app and onrender.com hosts.

If OAUTH_HTTPS_PROXY_REQUIRED appears, fix the host's trusted HTTPS forwarding setup rather than trusting arbitrary X-Forwarded-* input or relaxing HTTPS. A wrong trusted-ingress scheme now fails503 instead of redirecting endlessly. Configure trusted proxy addresses at hosting level if required; do not indiscriminately enable wildcard forwarding trust.

### Direct cross-site API alternative and its limits

SESSION_COOKIE_SAMESITE=none is available only with SECURE_COOKIES=true. Retain exact Origin allowlisting, credentials:include and CSRF tokens. Update CSP connect-src deliberately if choosing a direct API architecture. This option does not overcome Safari/mobile/embedded-browser third-party-cookie restrictions. The first-party proxy above is the recommended configuration. Do not spoof a browser user agent to bypass Google restrictions; open Safari/Chrome directly when in-app consent is blocked.

### Expected errors and callback handling

Anonymous GET /me401 and login401 for wrong password, unknown account or unverified/no-password email account are expected. They do not prove cookies failed. A successful login200 followed by /me401 is a session-persistence problem: the UI now stops with a cookie/session error instead of navigating as if authenticated. Email login lands on dashboard only after /me confirms the session. Protected pages wait for session loading and redirect anonymous users to sign-in. Logout/account deletion clear private client caches and land on sign-in; an already-expired logout401 still clears local identity.

Reusing an OAuth code/state must fail. API callers still receive400 for replay/missing/expired state. Browser HTML failures clear the transient cookie and redirect to a clean sign-in error URL, removing code/state from the address bar; refresh never automatically restarts OAuth. Logs contain only a safe reason code and request ID. A303 followed by later400s alone cannot distinguish expiry, a missing browser cookie and replay; use the new safe reason codes.

No push/deploy/cloud configuration changes were performed. Real Google consent, real mailbox delivery and real iOS/Safari behavior require manual post-deployment acceptance. Tests emulate mobile Chromium and synthetic remote Google signing/exchange boundaries; this is not proof that production is fixed.


## College demo: API and worker in one Render Free Web Service

This latest small-demo option runs the existing durable PostgreSQL worker inside the same web-service instance. It does not create a paid Background Worker or require Redis/scheduler infrastructure. It supersedes the separate-worker requirement for this deployment profile only; separate services remain the recommended scaling option.

**Render root directory:** backend. **Exact Start Command:**

```text
python -m app.serve
```

If the Render root remains the repository root, use `cd backend && python -m app.serve`. The Dockerfile default now uses app.serve too. Keep the existing dependency build command, production configuration, Neon URL, R2 bucket/prefix/credentials and stable STORAGE_KEY. No new mandatory environment variable is needed. Render supplies PORT; the launcher validates it and uses it for the API. Set the Render health-check path to `/api/v1/ready` so initial worker startup/consumer stalls are visible; `/api/v1/health` remains API liveness only. Do not add --reload or increase Uvicorn workers for this profile.

The supervisor launches exactly one Uvicorn process and one `python -m app.worker` process with inherited environment and unbuffered shared service logs. If either exits unexpectedly, the companion is stopped and the supervisor exits nonzero so the platform can restart the service. Linux SIGTERM/SIGINT requests stop both child process groups, with25 seconds total graceful shutdown and forced termination if needed. Windows development tests terminate owned interpreter trees. No deployment or production settings were changed by preparing this code.

The worker handles one job at a time, polls an idle queue every2 seconds, emits job/stage/failure metadata without document text, and retries transient SQLAlchemy errors with bounded backoff. It preserves database leases, heartbeat tokens, cancellation and existing explicit retry limits. Expired/missing processing leases become FAILED, including their extraction source status. AI work is never silently replayed after interruption; inspect provider usage and explicitly retry from the UI. Queued work remains durable and is claimed after the service wakes. A force-killed active job may remain PROCESSING until its last2-minute lease expires and the next claim pass recovers it.

Combined-service readiness uses a tiny ephemeral process-health file outside document storage; this is not persisted document data. A missing/stale worker heartbeat makes readiness503. Neon readiness still performs SELECT1. Original documents/reports continue to use private encrypted R2 storage in production, without a filesystem fallback. No schema/migration change is needed.

Source/analysis/discovery automatic polling pauses after10 minutes or an API error. The interface offers Refresh status and never labels a merely delayed job FAILED or cancels it automatically. Existing intake waiting already has a finite limit. Retry remains available only through the server's allowed states/attempt budget; the user does not need to re-upload preserved valid originals after a recoverable failure.

### Free-tier limits and demo preparation

Render Free can sleep after idle traffic, restart services, or terminate processes under memory pressure. Background CPU work does not provide an always-on guarantee. This implementation makes interruptions recoverable/visible; it cannot promise uninterrupted processing or an SLA. One API + one serial worker reduces concurrency but still shares the instance memory/CPU. Actual Render memory/load qualification has not been performed.

Use small authored demo files, keep the demo browser active, and confirm /ready plus worker logs before presenting. Optionally set MAX_UPLOAD_BYTES=5242880, MAX_PAGES=40 and MAX_DOCUMENT_TOKENS=20000 to reduce worst-case resource use. These are optional operator limits, not silently changed defaults. Choose a configured provider/model with sufficient permitted quota; rate limits, unavailable credentials, network failures and exhausted free AI quotas still cause clear failures. This profile creates no new paid service; it cannot make third-party AI free or unlimited.

Ensure applied migrations already match the application. Review retention: starting the worker also resumes the existing expiry/deletion-outbox maintenance policy, so expired retained documents may be removed by normal lifecycle rules. Never reset the database to clear a queued demo. Live deployment and real AI/R2 verification require your manual approval/execution; isolated tests do not certify production availability.


Existing queued uploads that outlived the browser's original wait may finish extraction as READY without an analysis job: open the preserved source and explicitly select a provider/consent and Analyze. The worker does not invent consent or trigger billable AI solely because a file exists. URL discovery likewise still requires policy selection. If Render uses Docker, remove a conflicting old Uvicorn-only start override or set it to python -m app.serve so the new CMD is honored.

Render's published Free limits also block standard outbound SMTP ports25/465/587. If the existing email transport uses those ports, live mail delivery is a separate hosting limitation; the queue fix does not bypass verification or silently substitute an email service. See https://render.com/docs/free .

## Persistent provider permissions and bounded orchestration

Registered users authorize providers once in Settings, choose a preferred primary, and save. Only checked providers may receive source text for analysis, context/semantic verification, chat and explicit explanation translation. Uncheck all and save to revoke all outbound AI access; revocations are rechecked before every HTTP attempt, including retries. Already transmitted content cannot be recalled. Legacy users with NULL permissions retain explicit per-analysis consent until saving permissions; no existing user is automatically opted in. Guest consent remains scoped to the individual analysis.

The preferred configured authorized provider runs first for extraction. Request size, failed availability and full-source context suitability determine which authorized configured model handles subsequent tasks. The app uses each provider's configured model ID; it does not invent model aliases or substitute arbitrary models. Fallback is bounded to three unique providers and at most three HTTP attempts per provider request. Exhausted unavailable/rate-limited providers are skipped for later tasks in the same operation. Safety blocks and exhausted operation budgets stop orchestration. Real job progress shows provider/model/task/attempt; model-call metadata retains transitions and failures.

HTTP 413 is PROVIDER_CONTEXT_LIMIT, not an outage. Wire-request budgeting includes serialized system/prompt/schema/metadata, estimated tokenizer allowance, output reserve and payload bytes. Source-aware re-chunking preserves original section offsets/pages. Semantic checks prefer models that can review the complete source. When that does not fit, up to 12 source windows can be audited for material exceptions/references before final verification; every returned excerpt is deterministically source-validated. Failed windows, unresolved context, excessive source size or exhausted budgets remain partial/ambiguous. This is model-assisted review, not independent proof or exhaustive legal certification.

Summary includes every supported category, source-linked overview facts, actual retained/verified/review counts and failure reasons. Unsupported/ambiguous findings remain inspectable in Detailed Analysis. Unestablished topics are review gaps, never proof that a provision is absent. No numerical risk score or invented narrative is generated; every document-specific overview statement comes from a supported finding.

An additive migration adds nullable users.authorized_providers. Apply `python -m alembic upgrade head` from backend through your approved migration step **before** starting the new backend/worker. Current head: b730a1410f91. No production migration was executed during development. PostgreSQL SQL was compiled offline and the upgrade/data-preservation/schema check was executed in a temporary SQLite database.

No existing Render/Vercel secret values need to change. Rebuild both frontend and backend after migration. Optional backend variables (never VITE_*):

- `PROVIDER_LIMITS`: JSON object keyed by provider or `provider/model-id`; supported positive integer fields are `request_tokens`, `context_tokens`, `max_output_tokens`, `max_payload_bytes`. Model-specific entries override provider entries. Calibrate to actual plan/model request limits; advertised context windows do not establish free-tier quotas.
- Defaults: Groq 6,000 estimated total request/output tokens and 2,048 output tokens; Gemini 24,000 total and up to 8,192 output; OpenRouter 12,000 total and 4,096 output. These conservative application budgets are not claims about provider entitlements.
- `MAX_AI_CALLS_PER_OPERATION=100`, `MAX_AI_TOKENS_PER_OPERATION=500000`: shared bounds across retries, fallback and verification for one analysis/chat/translation operation. Token accounting reserves estimated worst-case output, not a guaranteed dollar charge. Lower bounds to constrain usage. Provider rate limits and paid billing still apply.

Full live Gemini/Groq/OpenRouter availability, quotas and answer quality require a separately authorized real-provider smoke test. Automated integration coverage uses synthetic HTTP; no production records or live AI requests were used.
