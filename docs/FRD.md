VERIORA 2.0 — Functional Requirements Document (FRD)
Document ID: VER-FRD-001Version: 1.0 — Proposed baselineDate: 08 November 2026Owner: Business Analyst / Engineering Lead (to assign)Status: Review baselineTraceability: Feature IDs below map to PRD scope, TRD modules and Design screens.
1. Purpose and conventions
This document defines externally observable behaviors, states, constraints, success criteria and testable acceptance examples. MUST denotes a P0 release requirement unless annotated P1/P2; SHOULD denotes recommended behavior; MAY denotes optional enhancement. A “verified” result means verified against a captured source, not legally certified, factually executed by a company or guaranteed enforceable.
2. Actors, permissions and access
Actor
Allowed in P0
Not allowed
Guest
Limited upload/text/URL demo; transient results
Browse others' docs; durable export/library
Registered User
Own sources, analyses, questions, exports, deletion
Access other users' records
Reviewer (P1)
Assigned evidence annotation and sign-off
Modify captured original bytes
Admin
Operational health, aggregate metrics, abuse review
Read content by default without audited break-glass workflow
Backend worker
Process specific queued job under service identity
Cross-tenant arbitrary reads
MCP client (P1)
Authenticated scoped tools on authorized records
Bypass normal user permissions
Authentication and lifecycle
FR-AUTH-01 (P0): Sign-up/login/logout/session restore; server-issued HttpOnly Secure SameSite cookies, CSRF protection for browser mutations, email verification or approved equivalent; password hashing and account recovery.
FR-AUTH-02 (P0): Guest activity has a short-lived server-side capability scoped to the created analysis, with strict quota and expiry. Capability secrets must not be printed in logs.
FR-AUTH-03 (P0): Every resource lookup checks ownership, including results, source downloads, exports and job progress. Unauthorized or expired access returns non-revealing errors.
FR-AUTH-04 (P0): User may request deletion of source plus derivatives and gets an auditable confirmation of completed deletion; defined legal/operational audit retention exceptions must be disclosed.
3. Requirements matrix: ingestion and discovery
ID
Priority
Required behavior and acceptance outcome
FR-ING-01
P0
Accept PDF, DOCX, TXT and HTML through drag-drop/file picker; paste text. Reject unsupported or unsafe files with specific error.
FR-ING-02
P0
Enforce configured byte/page/token limits before model use; reject encrypted/password-protected files until unlocked.
FR-ING-03
P0
Store original bytes (or exact submitted text), source type, SHA-256 digest, acquisition time, owner and stable version ID.
FR-ING-04
P0
Extract text with page or paragraph anchors; retain source-order and normalization-to-original offset mapping.
FR-ING-05
P0
Detect missing pages where possible, zero/low extraction coverage, suspicious encoding and empty documents; prohibit “complete” status without evidence.
FR-ING-06
P0
Create deterministic document sections and chunks with token count, offsets, boundaries, overlap metadata and parent ID.
FR-ING-07
P1
Route scanned pages to OCR; emit OCR confidence and label estimated positions, not exact verified positions.
FR-URL-01
P0
Accept HTTP(S) website URL after strict SSRF validation; reject localhost/internal/private/metadata endpoints, dangerous redirects, credentialed URLs.
FR-URL-02
P0
Discover publicly accessible candidate legal pages via same-site links/footer/sitemap and allowed official linked locations.
FR-URL-03
P0
Show candidate URL, document type, origin link, retrieval status, timestamp and confidence; user selects what to analyze.
FR-URL-04
P0
Never assert all legal documents are found; report searched categories and inaccessible/missing candidates.
FR-URL-05
P0
Preserve resolved URL, fetch timestamp, ETag/Last-Modified where present, MIME type, source bytes/hash, redirect chain and discovered-from URL.
FR-URL-06
P0
Respect robots/terms, concurrency, size/time budgets, rate limits and user consent; do not bypass login or CAPTCHA.
FR-URL-07
P1
Store multiple policy snapshots and show old/new clause diffs with effective/observed dates separately.
Acceptance examples: (a) A website has privacy and refund policies but no accessible terms: the interface lists two candidates plus “Terms not found or not accessible,” never fabricates a terms URL. (b) A DOCX has 17 paragraphs: each verified citation identifies paragraph/section anchor. (c) A scanned PDF without OCR produces “Text extraction incomplete; analysis blocked or partial,” not a fabricated summary.
4. Requirements matrix: analysis and verification
ID
Priority
Required behavior and acceptance outcome
FR-AI-01
P0
Extract atomic claims classified CLAUSE, OBLIGATION, RIGHT, RESTRICTION, CONSENT, EXCEPTION, RISK_NOTE and OTHER when supported by schema.
FR-AI-02
P0
Every candidate records source version ID, chunk/section reference, quotation, rationale, prompt version, provider/model ID and raw status.
FR-AI-03
P0
Maintain document-only boundary by default. External knowledge cannot silently fill missing legal context.
FR-AI-04
P0
Verify quote presence and source coordinate deterministically before marking evidence as source-valid.
FR-AI-05
P0
Run semantic support check on claim relative to quote plus surrounding context; distinguish SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, AMBIGUOUS.
FR-AI-06
P0
A claim is displayed as “Verified against source” only when source location is valid and semantic support is SUPPORTED; partially supported is visibly caveated.
FR-AI-07
P0
Unsupported/ambiguous results remain inspectable and are never silently converted into verified findings.
FR-AI-08
P0
Deduplicate the same normalized finding tied to the same source span/category; retain materially conflicting clauses and references.
FR-AI-09
P0
Capture cross-references and exceptions; do not present a broad rule while omitting material exception in the cited context.
FR-AI-10
P0
Show analysis coverage: processed vs skipped pages/sections/chunks, extraction quality and failed provider calls.
FR-AI-11
P0
Provider router supports configurable generation and verification roles, budgets and explicit fallback; a fallback is recorded in run metadata.
FR-AI-12
P0
Track token estimates/actual usage, provider failures, retry count and cost estimate if pricing is configured.
FR-AI-13
P0
Query results and risks use calibrated labels or qualitative explanations, never arbitrary confidence percentages.
FR-AI-14
P0
If supporting evidence is missing, abstain: “I cannot confirm this from the available document.”
FR-AI-15
P1
Add cross-document conflict detection using both quoted source spans and labeled unresolved conflicts.
FR-AI-16
P1
Support expert review actions (approve/reject/rewrite) and immutable review histories.
Evidence status rules
Quote location
Semantic support
Public-facing status
Interaction
EXACT / NORMALIZED
SUPPORTED
Verified against source
Link to exact original span
EXACT / NORMALIZED
PARTIALLY_SUPPORTED
Partially supported
Show missing qualifiers/exception
EXACT / NORMALIZED
UNSUPPORTED
Unsupported interpretation
Show quote and warning; do not accept
EXACT / NORMALIZED
AMBIGUOUS
Needs review
Show competing interpretations
OCR_ESTIMATED
Any
OCR-based; requires review
Highlight approximate region, not “exact verified”
INVALID
Any
Source reference invalid
Never show as verified
Control: The verifier must not create new independent findings during verification; a new claim must restart candidate generation and full verification. A same-family generator/verifier is acceptable for an MVP with disclosed limitations, not independent proof. Human labels are the external ground truth for evaluation.
5. Requirements matrix: Q&A, viewer, search and exports
ID
Priority
Required behavior and acceptance outcome
FR-QA-01
P0
Users ask natural-language questions scoped to one analysis/source set; answers cite one or more retained evidence spans.
FR-QA-02
P0
A question whose answer depends on missing source content returns a qualified refusal/uncertainty and suggests what is needed.
FR-QA-03
P0
Answers describe exceptions and contradictions relevant to the exact question; no unqualified universal claims.
FR-QA-04
P0
Store user questions, cited finding IDs and provider metadata for registered users with retention controls.
FR-UI-01
P0
A finding click opens its source and scrolls to page/paragraph with precise highlight when available.
FR-UI-02
P0
Results filter by category, evidence status, document and keyword; all filters persist in URL query parameters.
FR-UI-03
P0
Dashboard shows processing status, last analysis, actionable notices and real data—not hardcoded metrics.
FR-UI-04
P0
Every async operation has pending, partial-success, failed, retryable, canceled and completed states as applicable.
FR-UI-05
P0
Mobile and desktop analysis navigation work without hiding evidence; keyboard-only flows are possible.
FR-EXP-01
P0
Export PDF analysis report containing source ID/version, date, findings, evidence quotations, limitations and verifier metadata.
FR-EXP-02
P0
Export machine-readable JSON verification manifest with hashes/IDs/location metadata; no forged trust seal.
FR-EXP-03
P0
Downloading original source obeys ownership, license/source restrictions and retention policy.
FR-EXP-04
P0
Deleting an analysis invalidates temporary links, derived chunks, prompts and report artifacts according to policy.
FR-EXP-05
P1
Add separately timed/signed evidence bundle with documented chain-of-custody process.
FR-CMP-01
P1
Compare two source versions/documents with original passages aligned and uncertain matches labeled.
FR-REV-01
P1
Reviewer sign-off shows reviewer identity, timestamp, reason and scope; never overwrites raw model output.
6. Screen inventory and UI state requirements
Screen / route
P0 purpose
Required states
Landing /
Explain value and limits, start analysis
Normal, service-degraded
Analyze /analyze
Upload, text, URL entry
Empty, drag-over, invalid, ready, uploading
Discover /discover
Inspect candidates and select sources
Loading, found, none, blocked, partial
Processing /analysis/:id
Same results route with job status
Queued, parsing, chunking, generating, verifying, partial, failed, complete
Results /analysis/:id
Insights, filters, evidence viewer, Q&A
Loaded, no findings, incomplete, error
Library /library
Saved sources and history
Populated, empty, paginated, deletion confirm
Account /settings
Data controls, retention, provider settings
Normal, validation errors
Login /sign-in
Account/session
Sign in, recover, verify email, error
Compare /compare
P1 pairwise comparisons
Source select, diff, unresolved
Always distinguish “0 findings” from “analysis failed” and “source has no such rule” from “rule cannot be determined.”
7. Processing state machine
CREATED -> QUEUED -> FETCHING/UPLOADING -> VALIDATING -> PARSING        -> CHUNKING -> GENERATING -> VERIFYING -> AGGREGATING -> COMPLETED                                              |                 |                                              v                 v                                      PARTIAL_COMPLETION     COMPLETEDAny active stage -> FAILED / CANCELED (with reason and safe retry policy)
A job transition is stored atomically. No UI animation may imply a completed stage before the server reports it.
Progress represents completed discrete work units (pages/chunks/findings) where measurable; otherwise show stage, not invented percentage.
Client reloads state by job ID. A browser close does not kill a persisted job.
On quota exhaustion, show provider-limit reason, whether any partial findings are safe to view and a retry time only if provider supplies one.
Retrying a job uses idempotency key and avoids duplicate source versions and duplicate billable calls where possible.
8. Sample acceptance scenarios (Given / When / Then)
Test ID
Given / When
Then
AT-01
User uploads a DOCX with numbered sections
Every supported finding links to its original section/paragraph
AT-02
AI invents “page 99” for 8-page PDF
Quote/location validator marks INVALID and UI does not show Verified
AT-03
Clause says “except where required by law”
Explanation includes legal-disclosure exception, not a blanket promise
AT-04
Privacy-policy URL returns 403
Candidate marked inaccessible and excluded from unqualified conclusions
AT-05
Malicious HTML contains “ignore instructions”
Parsing treats text as source data; worker never executes arbitrary requested actions
AT-06
Guest tries another session’s analysis ID
Response denies access without revealing source title/content
AT-07
User removes a document
Source and derived content become inaccessible; retention exception logged
AT-08
Model rate limit reached after 6/10 chunks
Status PARTIAL, identifies uncovered chunks and forbids “complete” label
AT-09
Same source passage produces duplicate candidate
One normalized finding shown, all originals recorded for traceability
AT-10
Document lacks a retention period
Response says unavailable/not stated only if coverage permits; never invents 30 days
AT-11
Source includes a cross-referenced appendix not uploaded
Analysis marks dependent finding incomplete pending appendix
AT-12
A finding is partially supported
Badge explicitly indicates partial; unsupported portion is described
AT-13
Download manifest
Hash re-computed against retained file matches recorded SHA-256
AT-14
Keyboard user focuses a finding
Can open and navigate evidence with no mouse interaction
AT-15
A PDF has only scanned images in P0
System warns scan/OCR required rather than generating empty or fictitious analysis
9. Non-functional functional contracts
Request/input limits documented and server-enforced; preliminary MVP values (tune after pilot): upload up to 20 MB, maximum 150 pages, 1 active job per guest / 2 per registered user, URL scan at most 20 candidate pages per request, limited depth and time. These are proposed operational defaults, not a promise of free processing for every accepted file.
Privacy disclosures precede third-party processing. No source text or secrets appear in analytics, access logs or exception messages.
P0 English support is explicit; untested translation is not certified semantic equivalence.
Each tool/provider/schema version is recorded. If validation cannot complete, result is flagged with reduced status, not hidden.
Report endpoints never bypass tenant access rules; report generation is traceable.
10. Business rules and terms glossary
Term
Precise meaning
Source
Specific acquired file/page URL or pasted text, plus bytes and metadata
Source version
Immutable instance of that source at capture/submit time
Section
Structure-aware region: page, heading, clause, paragraph or HTML block
Chunk
Bounded model input referencing exact source sections and offsets
Finding
Atomic structured assertion derived from source content
Evidence span
Extracted supporting original passage with locatable coordinates
Verified against source
Source location valid and semantic support established by configured verifier; not a factual/legal warranty
Coverage
Which sections/chunks were accessible and processed, including omissions
Evidence Passport
User-visible source/claim/provenance/verification record
Evidence package
Export of permitted originals, metadata, report and integrity manifest
Policy discovery
Attempt to find accessible linked legal pages; not completeness guarantee
External research mode
Explicitly enabled and separately cited outside-document knowledge (P2)
11. Dependency and handoff matrix
Workstream
Required input
Produces
Blocks
Ingestion
Uploaded bytes / URL snapshot
Immutable source sections
AI pipeline
AI foundation
Sections + chunks
Candidate structured findings
Verification
Verification
Candidate + source mapping
Evidence validity and support
Trust UI/export
API and auth
Users and jobs
Authorized endpoints
Frontend and MCP
UI
Versioned API contracts
Accessible end-to-end flow
Release acceptance
QA
Contract fixtures + human annotations
Regression and evaluation report
“Verified” labeling and release
A feature is accepted only when automated tests, source-provenance assertions, expected failure cases, accessibility checks and owner review for its FR IDs have passed. Unimplemented P1/P2 requirements must not be presented as active functionality.
## 10 November 2026 amendment: new functional contracts

| ID | Required behavior |
|---|---|
| FR-AUTH-05 | Google authorization-code OIDC with PKCE S256, hashed expiring single-use state, nonce, JWT RS256 signature/issuer/audience/expiry/email checks and browser binding. Existing-account linking requires an authenticated CSRF-protected action and matching verified email; no automatic email collision merge. |
| FR-AUTH-06 | Email signup returns an anti-enumeration202 response and stores a pending registration/password hash separately. One-hour hashed token plus chosen password activates the account once. No verification bypass in development or production. Expired records are cleaned by the worker. |
| FR-AUTH-07 | TLS-delivered single-use hashed recovery token; validated12–128 character replacement; invalidate all sessions after reset. Unknown accounts and delivery failures use the same generic recovery response. Globally missing mail configuration returns503. |
| FR-SUM-01 | Optional summary preserves detailed findings/history/reports. Only supported findings with validated source quotes enter summary cards. Exact page/section links navigate to original retained text. |
| FR-SUM-02 | Versioned attention-1.0 rules produce Low/Moderate/High/Not Determinable with explanation, no percentages and visible company-conduct limitation. Failed/partial/unresolved coverage cannot be labeled Low. |
| FR-LANG-01 | Validate en/hi/hinglish, persist registered preference, allow per-workspace override; translate statement/rationale/qualifications separately without changing any quote, page, offset or status. |
| FR-LANG-02 | Explicit authorized-provider translation, strict ID/schema check, separate fidelity review and fingerprinted PostgreSQL cache. Failed/unverified translation leaves the original analysis accessible. GET requests never initiate paid translation. |
| FR-LANG-03 | Natural English/Hindi/Hinglish question, authorized scoped retrieval, original-source quote validation and independent answer review; insufficiency abstains in selected language. Store answer language and registered conversation history. |

Verification/reset links place tokens in URL fragments; browser removes tokens from its visible URL after capture. Endpoints never echo tokens. Test-only mail capture is a transport for isolated tests, not a fake OTP or activation bypass. Scope and executed results are in REQUIREMENTS_AUDIT.md and VERIFICATION.md.

## Current amendment — additional acceptance contracts

| ID | Required behavior |
|---|---|
| FR-AUTH-08 | Email-only registration/start returns a neutral202 response, no account/password creation. Verification consumes the emailed one-hour token and issues a separate hashed15-minute setup capability. Complete requires matching validated password/confirmation and consumes setup once; only then activates the account. |
| FR-LANG-04 | Header globe selector applies English/Hindi/Hinglish across route UI, dashboard, summary, details, evidence, chat and report exports. PATCH /me/language is authenticated/CSRF-protected and persists independently of retention/provider settings. Navigation/reload preserve preference. |
| FR-LANG-05 | Static UI messages require no AI calls; every wired key has Hindi/Hinglish catalog entries. Cached explanation translations are prepared once per findings fingerprint/language; error states preserve original explanations. Quotes, coordinates, hashes and provenance stay authoritative and unchanged. |
| FR-UI-06 | Summary has a responsive evidence-first risk header, meaningful warning state, category cards, unique supported-clause count and exact-source actions. Existing Detailed Analysis, history, filters, report generation and chat remain functional. |
| FR-EXP-06 | language query selects verified cached explanation text for JSON/PDF reports without an extra AI request. Missing translation returns409 rather than silently claiming translated output. Original quotes/explanations, coverage warnings and model metadata remain inspectable. |

The old /auth/register and /auth/verify endpoints retain their original password-first behavior for compatibility with outstanding clients/links. The current React registration UI exclusively uses /auth/registration/start, /verify and /complete. Public account-existence checks are absent. SMTP accepted delivery is distinct from confirmed inbox receipt; Google consent-page reachability is distinct from a completed user-approved OIDC callback.


## 2026-11-10: final UI and deployment preparation

Extension requirements UI-FINAL-01..04: Summary default on entry; visible Summary/Detailed tabs; Processing Coverage exclusively at the bottom of Detailed Analysis; expandable exact source/context and category-limited clauses. BRAND-01: /logo.png with load/error-safe fallback, consistent responsive sizing and current-year footer. CHAT-SUGGEST-01: localized suggested questions derive from actual supported finding categories, with no additional AI call. OPS-STORAGE-01: production encrypted S3 adapter, development filesystem preserved. OPS-RESET-01: read-only document cleanup plan, separately approved backup-gated development/staging execution, never production. Deployment must not change existing credentials/data.


## Cleanup and hardcoding review (10 November 2026)

UI-CLEAN-01 requires a dot-free wordmark, hover/active/keyboard focus navigation and reduced-motion compliance. UI-CLEAN-02 requires expandable Summary guidance, neutral localized question prompts and localized page citation labels. CONFIG-CLEAN-01 requires frontend environment-file proxy overrides and production loopback-target rejection. This cleanup must not modify PostgreSQL records or .env.

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
