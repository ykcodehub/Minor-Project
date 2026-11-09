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
- Supply S3 credentials through host process secrets or IAM roles using the standard AWS SDK chain. Grant only required GetObject/PutObject/DeleteObject access to the private application prefix; block public access. The adapter encrypts bytes with the existing Fernet key, uses AES256 storage encryption and conditional PUT to prevent overwrite, validates object identifiers and bounds reads. The selected S3-compatible service must support these operations. SDK-mocked roundtrip/failure tests pass; a real bucket/IAM/lifecycle smoke test remains required.
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
