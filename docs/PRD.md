VERIORA 2.0 — Product Requirements Document (PRD)
Document ID: VER-PRD-001Version: 1.0 — Proposed baselineDate: 08 November 2026Owner: Product Owner / Project Lead (to assign)Status: Ready for review; implementation not yet authorizedCompanion documents: FRD (VER-FRD-001), TRD (VER-TRD-001), Design (VER-DES-001)
Product promise: Understand every clause. Verify every claim. Veriora explains what a document states, shows the original supporting evidence, and preserves an auditable record. It never equates a policy statement with proof that an organization followed the policy.
1. Executive summary
Veriora is a source-grounded document-intelligence application for contracts, privacy policies, terms and conditions, NDAs, employment agreements, service agreements and related documents. Users may upload a document, paste text or provide an official website URL. Veriora identifies available legal documents, analyzes selected sources, extracts obligations, rights, restrictions, exceptions and potentially concerning terms, and links every substantive finding to evidence in the exact source version analyzed. Users can navigate from a finding to the relevant passage. The platform reports omissions, ambiguity, OCR limitations and unsupported findings instead of inventing conclusions.
The rebuild starts from a clean codebase; the prior React/Vite UI is a visual reference, not a binding implementation. The old backend is not migrated wholesale. Provenance, validation, privacy controls and a repeatable test benchmark are product foundations, not add-ons. MCP may later expose the same trusted backend capabilities to external AI clients; it is not the core processing engine.
2. Problem and opportunity
People routinely accept long agreements without knowing what they permit, forbid or omit. Generic AI summaries may omit exceptions, invent page references, misread cross-references or confuse a company's promise with evidence of compliance. It is particularly difficult to preserve the version of a policy presented at a relevant time. Veriora's opportunity is to make document interpretation inspectable: each conclusion has an origin, evidence status, and disclosed limitations.
Trust model: Trust is earned through independently checkable source material, deterministic validation, expert-reviewed evaluation, secure data handling and transparent uncertainty. No release may advertise 100% accuracy, legal certification, guaranteed admissibility, or proof of real-world compliance.
3. Vision, principles and success outcomes
Evidence before assertion: A substantive finding must identify a source passage or carry an explicit unsupported/uncertain status.
Document-only by default: Answers must use only the analyzed source set. External law, websites or model knowledge require an explicitly enabled separate research mode and separate citations.
Source completeness is visible: Missing pages, inaccessible URLs, unparsed attachments, low-confidence OCR, and incomplete linked terms are prominent.
Original text is preserved: Source bytes, hashes, acquisition metadata, page/paragraph anchors and version references are reproducible.
Accessible by default: The first meaningful task should require little explanation, with simple-language output and optional professional detail.
Security over convenience: Confidential documents are not silently sent to third-party AI providers; users choose the applicable processing mode.
Modular, lean development: Only implement folders, packages, services and infra that serve a documented requirement.
Outcome targets (engineering goals, not verified performance claims)
Goal
Proposed release-gate target
Measurement
Invalid source coordinates accepted as verified
0 in mandatory adversarial test fixtures
Automated provenance checks
Unsupported claims labelled “fully supported”
Report confusion matrix and require product-owner sign-off; target 0 in critical safety fixtures
Human-adjudicated evaluation
All verified findings navigable to source
100% of verified outputs
End-to-end test
Visible document coverage statement
100% of completed analyses
Contract/UI tests
Audit log for evidence-package generation
100%
DB integration test
Accessible core journeys
WCAG 2.2 AA as target
axe, keyboard and manual testing
User control over retention/deletion
Implemented and validated
Deletion/integration tests
Numeric quality thresholds beyond those above must be set from a labeled pilot benchmark. Do not invent precision, recall, latency or legal reliability percentages.
4. Users and jobs to be done
Persona
Core job
Important constraint
Everyday consumer
Understand privacy, consent, refunds and cancellation before using a service
Plain language, low cognitive burden
Employee / freelancer
Locate obligations, restrictions and dispute clauses in contracts
Exact wording and referenced schedules
Small business / procurement reviewer
Compare terms and find conflicting commitments across documents
Repeatable structured exports
Legal professional
Inspect evidence and override interpretations with documented reasons
Never position AI as replacement for counsel
Researcher / QA evaluator
Compare models, verify findings and calculate quality metrics
Versioned datasets and reproducible prompts
Institutional reviewer (future)
Inspect acquired source, audit trail and review actions
Provenance, privacy, access controls; no certification claim
Roles: Guest (limited ephemeral analysis), Registered User (saved library and exports), Reviewer (P1 adjudication), Administrator (operations). Institution-specific roles are P2. All authorization is enforced by the server, including MCP tools.
5. Scope, release boundaries and explicit exclusions
P0 — Trustworthy MVP is the first development goal. P1 adds sophisticated review and history. P2 is an interoperability/institutional expansion, not a dependency for P0.
Capability
Priority
Definition
Upload PDF / DOCX / TXT / HTML and paste text
P0
Safe validation, document parsing and normalized provenance
URL-to-policy discovery
P0
Find and list accessible official linked policy documents; do not claim complete discovery
User review of discovered sources
P0
User confirms which sources are analyzed
Token-aware structured chunking
P0
Clause/paragraph boundaries, bounded overlap, source maps
Grounded clause/rights/obligations/risk extraction
P0
Structured, deduplicated and source-linked findings
Multi-stage source/evidence verification
P0
Exact/normalized quote match, location checks, semantic support classification
Document Q&A
P0
Evidence-first answers; explicit abstention
Dynamic analysis workspace
P0
Stage progress, source preview, finding filters, errors/retry
User sessions, private library, delete/export
P0
Secure saved records; limited guest trial
Report export and basic evidence manifest
P0
PDF report + machine-readable verification summary
Provider abstraction with one active + one tested fallback
P0
Configurable Gemini / Groq / OpenRouter adapters; available models depend on access
Scanned/OCR document path
P1
OCR quality disclosure and mapped source locations
Policy snapshot comparison / change alerts
P1
Versioned captures and diff of meaningful clauses
Cross-document inconsistencies
P1
Contradictions across related policies; show both sources
Reviewer sign-off and annotation
P1
Human review, history, reasons, immutable audit trail
Signed/timestamped enhanced evidence bundles
P1
Optional RFC 3161 timestamp service; avoid legal certification claims
MCP server for trusted analysis tools
P1
Separate authenticated tool surface over shared services
External legal-research mode
P2
Jurisdiction-specific legal sources separately cited and dated
Institutional deployment, SSO, advanced controls
P2
Procurement/compliance requirements and expert review
Out of scope for P0: court filing/admissibility guarantees; legal advice; prediction of litigation outcome; checking whether companies actually obey policies; hidden/signed-in content bypass; unrestricted web crawling; automatic legal judgement scores; unsupervised mass policy monitoring; unlimited free AI calls; broad autonomous agent actions; native mobile apps; real-time collaboration; blockchain; custom-trained foundation model.
6. Key user journeys
Journey A — Upload and understand a contract
User selects “Analyze a document,” uploads a supported file or pastes text, and sees privacy/AI-provider disclosure before processing.
System validates type and size, stores an encrypted source, computes hash, checks parsing coverage and produces source anchors.
User sees processing stages and can safely navigate away; job can be resumed.
Results show a concise overview, material findings, caveats, and source coverage.
Selecting any verified finding opens a synchronized document viewer with the exact supporting span highlighted; surrounding context is visible.
User asks “Can my data be shared without consent?” The assistant responds with cited clauses, exceptions and clear uncertainty.
Registered user exports a report or deletes the source and derived records.
Journey B — Analyze a website by URL
User enters website URL. System checks network safety and discovers linked official policy candidates.
Candidate cards show type, exact source URL, discovered-from page, capture status, language, and acquisition date.
User selects accessible sources; the system records missing/inaccessible policy categories instead of fabricating them.
Each policy is independently parsed and linked. A combined overview shows per-policy claims and source separation.
User may inspect each source; future version comparisons are P1, not silently inferred from current pages.
Journey C — Preserve a disputed clause
User selects a finding and opens its Evidence Passport.
Passport shows original quotation, paragraph/page/clause anchor, source hash, acquisition timestamp, model and verifier run ID, and review status.
Downloaded bundle contains the captured source (subject to source/license policy), report, manifest and audit metadata.
Product explains that a hash or report is not proof of a company's behavior, authenticity of remote origin, enforceability or court admissibility.
Journey D — No answer / incomplete document
System never fills gaps with common-sense legal expectations. It states whether the content is absent in a complete source, merely not found, inaccessible, poorly extracted, or ambiguous, and offers a document-specific next action.
7. Detailed product behavior and constraints
Evidence states: SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, AMBIGUOUS, plus technical citation-validity status EXACT, NORMALIZED, OCR_ESTIMATED, INVALID. Only supported claims with validated source locations receive the “Verified against source” label; never display 99% certainty without calibration.
Source version: Every finding points to a particular immutable captured document version; changing a document generates a new version, not overwritten evidence.
Risk labels: “Needs attention,” “Potentially restrictive,” and “Review recommended” describe interpretations, not legal invalidity. Each risk rationale includes the triggering text and exceptions. Risks do not become definitive findings of unlawful behavior.
Provider consent: Before transmitting document content to external models, show destination provider class, retention caveat and selected mode; no keys in browser. Confidential mode must disable external transfer unless a qualifying approved processor is configured.
Guest limits: Short-lived anonymous session; default retention maximum 24 hours, configurable only downward for stricter deployments. Saved history and full export require account. Abuse limits by file size/rate, not hidden surprise charges.
Registered retention: Proposed 30 days after last use by default, configurable user deletion and optional shorter retention. Actual product wording must match implemented and provider-side behavior.
Multi-language: English input/output is P0; Hindi/Hinglish explanations are P1 unless a pilot shows sufficient translation quality. Original citations always retain source-language text.
Research integrity: Keep original prompts, prompt version, model ID, generation settings, run timestamps and outcome labels for reproducible evaluation without exposing private content unnecessarily.
8. Product quality, UX and governance
The default UX must use a professional neutral visual system, no emojis, only consistent line icons where they improve understanding, no fake live progress, no fake security badges, no unverified “100% accurate” statement. Support empty/loading/partial/error states, responsive layouts and keyboard operation. All public-facing trust copy must accurately distinguish “document says,” “AI interprets” and “independently verified.”
Any expansion beyond P0 requires a short change note with purpose, acceptance criteria, risk, new files/dependencies and owning developer. Avoid adding a feature solely because a package or SaaS provider offers it.
9. Dependencies, assumptions and open decisions
ID
Decision / assumption
Proposed baseline
Owner
DEC-01
Primary launch jurisdiction
Jurisdiction-neutral document-only interpretation; no governing-law opinions
Product lead
DEC-02
Backend
FastAPI + PostgreSQL + isolated worker
Tech lead
DEC-03
AI
Configurable external provider; no guarantee of ongoing free-tier service
AI lead
DEC-04
Storage
Local in development; private object storage in production
Backend lead
DEC-05
Guest access
Limited guest evaluation; registered account for persistent evidence
Product/security
DEC-06
OCR
Mark as P1; scanned PDFs flagged as requiring OCR in P0
Product/AI
DEC-07
MCP
P1, shared services first; never replace core REST APIs
Tech lead
DEC-08
Historical evidence
P0 capture only current accessible sources; archive/change detection P1
Product lead
DEC-09
Document export
P0 PDF report + JSON manifest; source redistribution controlled
Security/legal
Any unresolved decision affecting privacy, security or legal claims blocks its related release path.
10. Milestones and completion gates
Gate
Deliverable
Evidence required
G0 — Specification approval
Four versioned docs, assigned owners, scope
Product and technical sign-off
G1 — Data foundation
Ingestion, format checks, provenance, DB migrations
Parser/source-map unit tests
G2 — Verified AI
Chunking, model router, extraction, semantic verification
Gold-label pilot and adversarial tests
G3 — Application
Dynamic UI, Q&A, URL discovery, export
Full E2E journeys including failure states
G4 — Security and release
Private access, retention/deletion, risk controls, monitoring
Threat review, test reports and acceptance
G5 — Expansion
P1 reviewer/versioning/MCP modules
Independent acceptance decisions
Definition of product done: A new user can analyze at least one supported source; all verified findings link to exact captured evidence; incomplete data and AI uncertainty remain visible; no protected document leaks across sessions; exported metadata can be reconciled against its source; benchmark and limitations are published internally.
11. Collaboration and change management
The PRD owns why/what/priorities; FRD owns exact functional behavior; TRD owns implementation contracts; Design owns interface rules. Each ticket uses a requirement ID and acceptance checks. Feature ownership may be reassigned without reworking the project structure. One reviewer approves cross-module API changes. All four specifications are versioned in Git and updated in the same PR as material behavior changes.
## 10 November 2026 amendment: identity, summaries and languages

This user-authorized extension promotes Hindi/Hinglish explanations and Google sign-in into the current implementation scope. Original evidence remains in its source language. Accounts become active only after email ownership verification or a verified Google identity. Pending email registrations are separate and expire after one hour; verification also requires the chosen password to prevent pre-registration account takeover. Google identities are bound by stable subject, not automatically linked by matching email. Existing verified accounts/data are preserved.

The results workspace adds an optional Summary/Detailed Analysis toggle. Short benefit, duty, restriction, risk and exception cards link to original evidence. Low/Moderate/High are transparent document-attention categories, not predictions of legal outcomes or company conduct; insufficient verified evidence produces Not Determinable. English, Hindi and Hinglish preferences persist for registered users. Changing language translates explanations only after an explicit provider request, validates fidelity and caches the result separately. Document-scoped chat accepts informal multilingual questions and preserves exact citations.

Acceptance remains partial for external integrations: Google and SMTP credentials are missing. Isolated email-token/browser/OIDC-signature checks run, but live Google/mailbox delivery is not certified. Groq live Hindi/Hinglish translation and English cited answering passed; Hindi/Hinglish live answers hit rate limits. Human linguistic/semantic evaluation remains a release gate.

## Current amendment — global language, email-first signup and Summary refinement

The current registration experience starts with only an email address. Email ownership is proven before password creation; the user then chooses and confirms a password. No active user or password is created during the email stage. Existing verified accounts, Google identities and older issued signup/verification API contracts remain supported.

Language belongs to the application header globe menu, not an individual analysis. English/Hindi/Hinglish changes update UI/navigation immediately and persist in PostgreSQL for both account and guest sessions; anonymous visitors retain a browser preference. Saved analysis explanations use fingerprinted verified caches. UI catalog translation is static and does not send user content or create runtime provider calls. Non-English document explanations can still fail explicitly on provider/quota issues; original source quotations never change.

Summary keeps the Detailed Analysis toggle and existing evidence workflows. It presents a distinct document-risk panel, explicit warnings, benefits, obligations, restrictions, critical clauses and method notes. Risk labels retain the documented conservative rules, with Not Determinable for insufficient support. They do not certify company conduct, enforceability or legal outcomes. Localized reports preserve exact source quotes and original explanation metadata.


## 2026-11-10: final UI and deployment preparation

The analysis entry point defaults to Summary; Detailed Analysis remains a visible top-level choice. Users see evidence-grounded risks, benefits and obligations before technical coverage. Expandable source/context and bounded cards reduce default scrolling. Branding uses a supplied /logo.png with a safe fallback and dynamic-year footer. Production release requires a separately hosted API/worker, fresh PostgreSQL and qualified private object storage; configuration preparation is not a deployed product.


## Cleanup and hardcoding review (10 November 2026)

UI cleanup preserves real PostgreSQL-backed documents and verified findings. Brand punctuation is removed, navigation remains accessible with reduced-motion support, and longer explanation guidance is progressively disclosed. No fabricated users, analysis results or numerical confidence indicators were introduced.

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
