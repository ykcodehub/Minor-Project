VERIORA 2.0 — Technical Requirements Document (TRD)
Document ID: VER-TRD-001Version: 1.0 — Proposed baselineDate: 08 November 2026Owner: Technical Lead (to assign)Status: Technical proposal; freeze after reviewGuiding rule: Modular monolith first. No microservices, queue broker or vector database without a demonstrated requirement.
1. Architectural decisions
ADR
Decision
Rationale and trade-off
ADR-01
Frontend: React 19, TypeScript, Vite, Tailwind CSS, React Router
Modern, typed, maintains visual continuity with previous React app
ADR-02
UI: Lucide icons + minimal accessible headless primitives
Consistent professional UI; avoids oversized component framework
ADR-03
Backend: Python 3.12+, FastAPI, Pydantic v2
Parsing, model SDK ecosystem, typed APIs
ADR-04
Persistence: PostgreSQL 16+, SQLAlchemy 2, Alembic
Transactions, relational provenance, JSONB for controlled flexibility
ADR-05
Durable work: PostgreSQL-backed job lease + dedicated worker process
No Redis/Celery in P0; later migrate to broker if evidence demands
ADR-06
File storage: local private files for dev, S3-compatible private object store in prod
Database holds metadata; files not in public static directories
ADR-07
AI adapters: provider interface for Gemini, Groq, OpenRouter
Model routing independent of UI and business logic
ADR-08
Search: Postgres FTS + structured section/chunk lookup initially
Avoid unjustified vector DB; evaluate retrieval recall before pgvector
ADR-09
Source anchors: PDF page/blocks, DOCX paragraph, HTML DOM path, TXT ranges
Deterministic source navigation and quote matching
ADR-10
MCP: authenticated P1 adapter over existing services
Standard tool interoperability without duplicating logic
ADR-11
API version: /api/v1, OpenAPI schemas and contract snapshots
Parallel frontend/backend teamwork
ADR-12
Security: strict tenant isolation, SSRF protection, minimal privileges
Sensitive documents and user-controlled URL fetches
Free tiers: Provider models, quotas, data processing terms and pricing must be rechecked before deployment. Store provider IDs as configuration, not hardcoded product promises. Free-tier usage must be opt-in only for documents permitted by the selected privacy mode.
2. High-level architecture
             Browser (React + TypeScript)                 | HTTPS REST + polling                 v          FastAPI Application (API/auth)           |           |            |           v           v            v       PostgreSQL   Object Store    Job table           ^           ^            |           |           |            v           +-----------+------  Dedicated Worker                                 | parse / source map                                 | chunk / model router                                 | verify / aggregate                                 v                          AI Provider Adapters                         Gemini / Groq / OpenRouter  P1 MCP Server -> SAME authorized application services  (never direct database or unrestricted file access)
Web browser and MCP clients are untrusted principals. Both authenticate and authorize through the same service boundary. Public web documents are untrusted inputs, never instructions to the AI or an implicit tool-permission grant.
3. Repository structure — deliberately small
veriora/  README.md  .gitignore  compose.yml                 # Local PostgreSQL only  docs/    01_PRD.md    02_FRD.md    03_TRD.md    04_DESIGN.md  frontend/    package.json    tsconfig.json    vite.config.ts    index.html    .env.example              # VITE_API_BASE_URL only; no secrets    src/      main.tsx      app/                    # router.tsx, providers.tsx      components/ui/          # Reusable primitives actually used      features/               # analysis/, discovery/, library/, auth/ when built      lib/                    # api.ts, format.ts, types.ts      styles.css  backend/    pyproject.toml    .env.example    alembic.ini    migrations/              # Created with first schema migration    app/      main.py      config.py      db.py      models.py               # Start consolidated, split only when needed      schemas.py              # API contracts; split when cumbersome      security.py      worker.py      api/                    # auth.py, documents.py, discovery.py,                              # analyses.py, questions.py, exports.py      services/               # ingest.py, chunking.py, analysis.py,                              # verification.py, discovery.py,                              # model_router.py, export.py      providers/              # base.py, gemini.py, groq.py, openrouter.py      mcp/                    # P1 only: server.py    tests/      unit/      integration/      fixtures/               # Minimal synthetic / licensed files
Do not create placeholder feature directories, utils dumping grounds, __init__.py in every location unless Python packaging requires it, duplicate models layers, empty services, a shared/ workspace, Kubernetes, Docker images, Redis, Elasticsearch or a vector DB in P0 without an accepted ADR. README.md includes setup commands, chosen entry points and development ownership. Frontend keeps one shared component directory and feature-local components; avoid multiple nesting levels for single-use components.
4. Domain data model (minimum viable persistent schema)
Entity
Key fields
Important constraint
users
id, email, password_hash, verified_at, created_at
Email unique; PII protected
sessions
id, user_id, token_hash, expires_at
Revoke on logout/delete
sources
id, owner_id/guest_id, kind, original_name, object_key, sha256, source_url, captured_at, status, metadata
Original immutable
sections
id, source_id, ordinal, page, heading, clause_label, locator_json, text, offset_map, extraction_quality
Deterministic locators
chunks
id, source_id, chunk_index, token_count, original_span_map, content_hash, text
Structured overlaps tracked
jobs
id, owner, source_ids, type, state, progress_json, lease_until, attempts, error_code, idempotency_key
Durable transitions and leases
analyses
id, owner, job_id, scope_json, state, coverage_json, prompt_version, created_at
Captured scope immutable
findings
id, analysis_id, category, statement, rationale, severity_hint, support_status, original_candidate_json, verifier_version
Atomic statements
evidence_spans
id, finding_id, source_id, section_id, quote, start/end, locator_json, match_status
Must resolve to source
model_calls
id, job_id, provider, model, role, token_in/out, latency_ms, outcome, prompt_version, estimated_cost
No sensitive text in log rows
audit_events
id, actor_id, action, object_type, object_id, timestamp, metadata_json
Append-only; audited access
For P1 versioning, extend sources with stable policy_family_id and insert captures rather than overwriting; a dedicated policy_families table can be created only when change monitoring is built. Use UUID/ULID primary keys, timestamptz UTC, explicit foreign keys, unique constraints and supporting indexes for (owner_id, created_at), (analysis_id, support_status), and (source_id, ordinal). Enforce ownership in application service layer and consider PostgreSQL RLS defense-in-depth; never accept client-provided owner IDs.
5. REST API — versioned contracts
Method / path
Behavior
Main responses
POST /api/v1/auth/register
Account create; email verification flow
201/400/409
POST /api/v1/auth/login
Create secure session
200/401/429
POST /api/v1/auth/logout
Revoke session
204
GET /api/v1/me
Session/role
200/401
POST /api/v1/sources/upload
Multipart source ingestion
202 {source_id, job_id}
POST /api/v1/sources/text
Exact pasted-text source
202 {source_id, job_id}
POST /api/v1/discovery
Safely discover official policy links
202 {job_id}
GET /api/v1/discovery/{job_id}
Candidate list with statuses
200
POST /api/v1/analyses
Create analysis for selected authorized source IDs
202 {analysis_id, job_id}
GET /api/v1/jobs/{id}
Stage / progress / errors
200/403/404
GET /api/v1/analyses/{id}
Summary, coverage, counts
200/403/404
GET /api/v1/analyses/{id}/findings
Filter/paginate/sort findings
200
GET /api/v1/sources/{id}/sections/{section_id}
Evidence viewer data and source locator
200/403
POST /api/v1/analyses/{id}/questions
Evidence-grounded Q&A
200/422/429
POST /api/v1/analyses/{id}/exports
Queue report/manifest generation
202 {job_id}
GET /api/v1/exports/{id}
Authorized short-lived download
200/403/404
DELETE /api/v1/sources/{id}
Delete source + controlled derivatives
202 or 204
GET /api/v1/health
Liveness, no secrets
200
In production, require request IDs, schema validation, 4xx/5xx structured errors {code, message, request_id, details?} without stack traces or source text. Idempotent create endpoints accept Idempotency-Key. OpenAPI client types may be generated from the FastAPI schema; do not manually duplicate dozens of TypeScript domain contracts.
Analysis response minimum
{  "analysis_id": "a_123",  "status": "COMPLETED",  "source_ids": ["s_123"],  "coverage": {"sections_total": 42, "sections_processed": 42, "warnings": []},  "findings_count": 7,  "limitations": ["Interpretation is not proof of real-world compliance"]}
Finding response minimum
{  "finding_id": "f_123",  "category": "OBLIGATION",  "statement": "The policy requires user consent before third-party sharing, subject to an exception.",  "support_status": "SUPPORTED",  "citations": [{    "source_id": "s_123", "section_id": "sec_8",    "quote": "...", "page": 23, "clause_label": "8",    "match_status": "EXACT", "start": 180, "end": 240  }]}
IDs and numeric locations here are illustrative, not from a real contract. Quote offsets must be defined consistently relative to original source-extracted section text (UTF-8 byte offsets versus Unicode code point offsets must be chosen explicitly; recommendation: Unicode code point offsets in normalized extraction with source mapping to original and bounding geometry).
6. Processing and chunking algorithm
Stage 1 — Validation. Identify actual file type by content; antivirus/malware scan if deployment supports it; cap decompression size, PDF complexity, pages and HTML bytes. No macro execution or active embedded content.
Stage 2 — Extraction. PDF: PyMuPDF page text plus block geometry, reading order check; DOCX: headings/paragraphs/tables plus index; HTML: readable DOM with origin URLs/anchors; TXT: encoding detection plus line/character offsets. Each section retains original/cleaned text and mapping. A source can be text-extracted yet structurally incomplete.
Stage 3 — Canonicalization. Normalize whitespace/Unicode cautiously. Never replace original bytes. Track cleaned-span to original-span mapping; if mapping is unreliable, downgrade citation status.
Stage 4 — Token-aware segmentation. Split by headings, clauses, paragraphs and sentence boundaries. Use provider token counting where available; other providers use a conservative compatible tokenizer and enforce measured output budgets. Target a configurable chunk budget (initial pilot 1,500-2,500 tokens, max overlap 150-200 tokens). Do not split a short numbered clause unnecessarily. Every chunk has section IDs, normalized offset ranges and origin spans. Overlap is contextual, not separate evidence.
Stage 5 — Coverage and generation. For each chunk, prompt for atomic, quoted, structured candidates. Apply schema validation; retry boundedly for schema errors; never invent citations. A whole-document pass checks cross-references, exceptions and uncovered spans under the same run.
Stage 6 — Deterministic evidence matching. Verify source ID, section ID, quoted substring/normalized match, start/end bounds, page/anchor and content hash. Distinguish exact, normalized, OCR-estimated and invalid; never conflate matching quote with semantic entailment.
Stage 7 — Semantic support. Independent verification prompt/model role, using claim, exact source quote, neighboring section and documented rubric. Return support enum, rationale and missing qualifier. Verifier cannot fabricate new citations. Escalate disagreements to ambiguous/unsupported until reviewed.
Stage 8 — Merge and persist. Deduplicate by category + normalized claim + equivalent source span; retain all candidate IDs and exception relationships. Aggregate doc-level coverage and provider-call metadata. Commit versioned results transactionally.
Stage 9 — User Q&A. Retrieval filters only authorized chunks from selected source versions, with FTS and section label matching; answer requires cited span IDs; validation identical to normal findings. Avoid automatic external web search.
Stage 10 — Export. Compile evidence pass, limitations, source info, hashes, run metadata; check access and licensing.
If a source is OCR-only in P0, return an explicit capability-limit outcome; do not feed no-text PDF to an LLM. If performance proves FTS insufficient, evaluate embedding retrieval with labeled recall before adding pgvector. Any second model used for verification still needs human-ground-truth benchmarking.
7. Model router and provider contract
class ModelProvider(Protocol):    def generate_structured(self, *, role, messages, schema, budget, timeout): ...    def count_tokens(self, *, messages, model_id): ...    def health(self): ...
Roles: candidate_generation, semantic_verification, question_answering. Config values: provider ID, model ID, region/data-policy profile, request and token budgets, retry attempts, temperature, timeout, max output tokens, prompt version and fallback order. The worker does not expose raw API keys to the frontend; secrets live in environment/secret manager. For failing free-tier providers, use capped exponential backoff with jitter, then transparent fallback where policy allows; if privacy policy changes, require reconfirmation. Log exact model used in every run.
Avoid blind rotation across multiple providers for confidential documents; provider suitability and consent are part of routing. Provider APIs and free quotas change; verify at implementation time.
8. Job execution / concurrency
Start with database job queue using atomic claim (SELECT ... FOR UPDATE SKIP LOCKED or equivalent), lease expiration, heartbeat, attempt counter, idempotency key, cancellation flag and retryable error taxonomy. Run a distinct worker process, not long-running processing in the API event loop or browser. Keep generation timeouts bounded. Every stage writes progress and coverage counts. After restart, reclaim expired leases and resume/restart idempotently.
Worker code is kept in one process boundary in P0. If volume, scheduling or retries exceed DB queue limits, write an ADR before adding Redis/arq/Celery. UI polls GET /jobs/{id} with sensible exponential delay; SSE/WebSocket can be added after robust polling works.
9. MCP integration contract (P1)
Use official Python MCP SDK (current supported version pinned at implementation) and HTTP transport recommended by the chosen MCP revision. Expose only service calls that already enforce ownership, quota and evidence-validation rules. Example tools: list_my_documents, analyze_document, search_document_clauses, ask_document, get_evidence_passport, compare_policy_versions (P1). Read-only by default; side-effectful export/delete tools require additional approval and scoped permissions.
Scope access at document and account levels, protect tool inputs from prompt injection, validate all tool args server-side, and record tool calls in audit events. Avoid calling arbitrary URL fetch or shell tools from model-generated arguments. MCP compatibility and host-specific authorization must be tested, not assumed.
10. Security, privacy and abuse prevention
Identity: Argon2id password hashes, email verification, secure HttpOnly cookies, session rotation, CSRF protection and rate limiting. Use generic login errors and never log passwords/tokens.
Authorization: Every source, job, analysis, export and MCP tool checks tenant owner; test IDOR scenarios. Credentials and provider keys are server-only.
Untrusted documents: Sanitize HTML rendering; never execute embedded scripts/macros; distinguish system instructions from file contents; constrain model tool permissions.
URL fetch safety: HTTP(S) only, block private/loopback/link-local/metadata/IPv6 internal targets; resolve DNS and validate at connection; validate every redirect and prevent rebinding; no arbitrary ports; limit response bytes, depth, time and requests. Treat downloaded links as untrusted.
Encryption: TLS in transit; encrypted private object storage and DB backups; no publicly accessible source buckets; short-lived signed download URLs.
Privacy: Record user consent/provider processing profile; no source bodies in telemetry. Deletion propagates to database derivatives, object storage, cached exports and indexes; backup expiry documented. Guest cleanup enforced by scheduled worker task.
Audit integrity: Append-only audit events with actor, time, action, object ID, no secret values; document hash before and after export. Optional external trusted timestamp is P1.
Licensing: Discovery does not imply permission to redistribute copyrighted third-party policy documents. Restrict exports based on permitted use and source acquisition rules.
Regulatory claims: Evidence manifests do not imply legal admissibility or that an organization complied with a policy.
11. NFR targets and SLO proposal
Area
Proposed implementation target
Validation
Availability
Best effort in free-tier prototype; production SLO to be set after hosting choice
Synthetic uptime checks
Interactive API
P95 under 600 ms excluding uploads and generation in target test environment
Load test
Document processing
Stream stage updates; no fake fixed completion time
Job logs + UI E2E
Upload size
20 MB P0 default, server-configurable
Boundary tests
Document length
Up to 150 pages P0 subject to token/cost limits
Fixture tests
Citation location
100% syntactically valid for VERIFIED label
Provenance unit/E2E tests
Isolation
No cross-user data leaks in integration and security tests
Tenant adversarial tests
Accessibility
WCAG 2.2 AA target for core flows
Automated/manual audit
Observability
Every job has trace ID, stage state, provider ID, duration and redacted errors
Structured logs
Backups
Encrypted, restore tested; RPO/RTO defined for paid production deployment
Restore drill
These are design targets, not measured performance or availability commitments. Quality reports must include precision/recall/F1, support false-positive/negative rates, citation accuracy, human agreement, processing completeness, failure rates, tokens and actual cost. Repeated runs nested in documents must not be treated as independent samples.
12. Testing and engineering quality gates
Test category
Minimum required fixtures and gate
Parser unit
Multi-column PDF, DOCX table, HTML anchors, UTF-8 TXT, malformed/encrypted/empty docs
Chunking
Long clause, overlapping spans, page transitions, Unicode offsets, no text loss
Provenance
Positive exact/normalized match and negative forged page/quote/section
Verification
Contradictions, exceptions, partial support, unsupported and ambiguous claim sets
API contract
OpenAPI snapshot, schema validation, pagination, idempotency and error codes
Security
Cross-tenant IDs, file-content script injection, SSRF redirects/DNS, credential leakage
UI E2E
Upload, URL discovery, status resume, viewer navigation, Q&A, export, delete
Accessibility
Keyboard focus, screen reader labels, contrast, reduced motion, responsive
Provider resilience
429 quota, timeout, malformed JSON, provider outage, retry/fallback disclosure
Benchmark
Human-adjudicated gold evidence and report of confidence intervals; no fabricated accuracy
Use pytest (Python), Vitest + React Testing Library (front-end), Playwright for E2E, plus Ruff / type check, ESLint / TypeScript compiler in CI. Pin dependency versions with lockfiles. Run migrations in staging before production. No automated test may rely on secret keys in source; use mocks and synthetic documents.
13. Environments, configuration and deployment
Local: Vite + FastAPI API + worker + PostgreSQL via compose.yml, with private local file directory outside static assets. Staging mirrors production providers using test/limited keys and synthetic files. Production: static frontend hosting; HTTPS API service and separately deployed worker; managed PostgreSQL and private object storage. A serverless platform with short request duration limits must not host long synchronous analysis jobs; deploy a persistent worker-compatible host. Distinct CORS origins per environment; strict origin allowlist parsed as a list. Secrets never committed. Database migrations have rollback/forward recovery plan; backups and deletion job are monitored.
14. Engineering ownership and cross-team boundaries
Owner track
Primary files/modules
Interface contract
UI/Frontend
frontend/src/features, UI components and router
FR-UI, OpenAPI types, Design
Backend & security
backend/app/api, auth, DB, worker, storage
FR-AUTH, FR-ING, REST contracts
AI & evidence
backend/app/services/{chunking,analysis,verification}, providers
FR-AI, finding schemas and fixtures
Discovery & provenance
ingest.py, discovery.py, source locators
FR-URL and source-map schema
QA/Research
backend/tests, E2E fixtures, labeled benchmark
Acceptance and measured quality
Tech lead
ADRs, schema/API review, CI, migrations
Integration release gates
Interface changes are proposed as reviewed commits with updated examples and tests. One owner per requirement; no shared mutable folders without code review. Do not add a new infrastructure dependency unless an ADR documents the problem and measurable benefit.
15. References and standards to consult
Model Context Protocol specification: https://modelcontextprotocol.io/specification
MCP Python SDK: https://py.sdk.modelcontextprotocol.io/v2/
NIST AI RMF Generative AI Profile (2024): https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
OWASP prompt injection guidance: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html
OWASP SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SSRF_Prevention_Cheat_Sheet.html
WCAG 2.2 recommendation: https://www.w3.org/TR/WCAG22/
Gemini API pricing/data-use disclosure: https://ai.google.dev/gemini-api/docs/pricing
Bharatiya Sakshya Adhiniyam 2023 (Sections 61–63): https://thc.nic.in/Central%20Governmental%20Acts/Bharatiya%20Sakshya%20Adhiniyam%2C%202023.pdf
These sources are design inputs, not a claim of compliance. Reverify evolving SDK/API/provider specifications at implementation time.
## 10 November 2026 implementation amendment

Additive revision `dfda9673d7bc` creates pending_registrations, oauth_attempts, oauth_identities and localized_analyses; adds users.language with existing-row default en. No existing table/data reset. Pending secrets/state/nonce/verifier/token are hashed at rest; pending passwords use Argon2. The browser-only PKCE verifier/nonce live in a short-lived HttpOnly SameSite cookie. Successful Google subject identity uses shared session creation. JWT verification uses PyJWT[crypto], Google's fixed JWKS and token endpoints, pinned RS256, issuer/audience/expiry/nonce/email checks. Arbitrary third-party Google mailbox addresses without hosted-domain assurance use email signup instead. Explicit linking requires current verified session. OAuth callback query strings are redacted in Uvicorn access logs.

Reference: [Google OIDC validation](https://developers.google.com/identity/openid-connect/openid-connect) and [server ID-token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token).

SMTP uses STARTTLS with certificate validation and optional authentication. Missing SMTP fails signup closed in all non-test environments. Verification requires the chosen password to prevent accepting an attacker-prepared password. Token consumption uses row locks; reset removes all sessions. Deployment must retain HTTPS/secure cookies, origin restrictions, database permissions, SMTP operational monitoring and proxy log redaction.

Summary service revalidates source coordinates and uses attention-1.0 rules: incomplete/no valid/unresolved coverage -> Not Determinable; supported obligation/restriction/risk note with a positive high-attention English phrase -> High; other supported obligations/restrictions/risk notes -> Moderate; complete supported rights/permissions/exceptions only -> Low; unclassified scope -> Not Determinable. Positive phrases are unlimited liability, irrevocable license, rights/claims waiver, sale of personal data; a preceding no/not/never/without suppresses matching. This bounded lexical attention rule is not a legal-risk classifier and does not certify that all clauses were found. Original-language patterns outside this rule set may remain Not Determinable.

Translation is an explicit POST, using the original consented analysis provider/fallback policy. Strict per-ID output is reviewed for semantic fidelity and cached by full findings fingerprint+language. Quotes never pass through a translated evidence channel. Analysis-row lock/unique cache constraint reduce duplicate calls. Long translations beyond200 findings/48k characters fail explicitly. Non-English retrieval normalization is a model request to the same authorized route; final answers still use original chunks and exact citations. Model calls/answer language persist. Manual retries and concurrent chat can consume quota; no unlimited-free-tier assumption.

## Current implementation amendment — language and signup stages

Migration `0f439d83280f` adds only nullable pending_registrations.verified_at. Existing pending passwords/tokens and user records are preserved. New email-first pending rows carry an empty password sentinel. Row-locked verification rotates the primary-key token digest and records verification, reducing expiry to15 minutes. The setup bearer is returned only after possession of the single-use emailed token; no user exists yet. Confirmed password hashing/activation occurs atomically during completion. Legacy verification paths never accept an empty password hash. Guest upgrade remains bound to the original session and CSRF proof.

Global LanguageProvider uses a checked-in public-copy catalog, local anonymous preference, PostgreSQL profile language and serialized authenticated preference updates. It sets HTML lang to en/hi/hi-Latn. Components subscribe through shared context, not DOM mutation or page reload. The header globe controls navigation and all feature-page UI. Translation POST queries are deduplicated by analysis/language/fingerprint, with backend lock and unique cache guard; canonical findings and source quotes remain separate. Report exports use existing verified cache entries and do not initiate another provider call.

SMTP uses the existing credentials unchanged. A display-name-only MAIL_FROM is formatted with a validated SMTP_USER mailbox; malformed/injected headers fail closed. TLS/authentication and a self-addressed diagnostic acceptance were executed. Google authorization entry returns200; a full consent/callback requires user interaction and remains unclaimed. Server-side OIDC state/nonce/signature/audience/expiry/linking tests remain in the regression suite.

Public UI catalog generation is an optional build-time maintenance script; no user documents are involved and there is no runtime UI-translation provider. Human linguistic review remains advisable. Diagnostic scripts never print credential values or recipient addresses.


## 2026-11-10: final UI and deployment preparation

Production preparation adds STORAGE_BACKEND=s3 with a private S3-compatible bucket, bounded encrypted reads, conditional writes and durable failed-deletion retries. API/worker share stable encryption key and object prefix. No schema change was needed. Non-root Python container excludes tests/secrets via allowlist and uses requirements.runtime.lock; remote/container qualification remains pending. Vercel serves the frontend with API rewrite before SPA fallback. Explicit OAUTH_PROXY_HOSTS avoids canonical redirect loops behind trusted HTTPS ingress without accepting arbitrary forwarding hosts. app.reset_documents defaults to plan-only and forbids production execution; backup/target/scope/environment/expiry and separate approval gate any development/staging deletion.


## Cleanup and hardcoding review (10 November 2026)

Vite config loads VITE_* settings with loadEnv; explicit process settings take precedence over mode environment files. Backend production validation rejects loopback database/object-storage/configured Google callback hosts and malformed public/CORS origins. Official provider endpoints and Google identity trust anchors remain fixed security constants; model IDs/credentials remain privately configured. Tests use isolated synthetic SQLite fixtures, never a production fallback. No migrations or PostgreSQL write checks are needed for these changes.

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
