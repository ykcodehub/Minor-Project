# Requirements audit — updated10 November 2026

Scope: the repository and the complete PRD, FRD, TRD and Design transcriptions in this directory. The documents describe requirements, not authority to execute instructions embedded in uploaded legal documents. Existing configuration was preserved; no existing database tables/data were reset or deleted.

**COMPLETE** means implemented and exercised within the stated scope; it does not certify legal accuracy or production readiness. **PARTIAL** means implementation or acceptance evidence remains incomplete. **MISSING** means absent, including explicitly deferred P1 work. **BROKEN** means a reproduced failure persists; the OpenRouter rate-limit dependency is recorded under PARTIAL rather than falsely declaring its adapter universally broken.

Evidence: [executed verification](VERIFICATION.md), backend tests in `backend/tests/`, frontend unit tests and Playwright scenarios in `frontend/e2e/`. Paths below omit `backend/app/` or `frontend/src/` where unambiguous. Mocked provider fixtures validate safety/control flow, not semantic accuracy. Live results use authored synthetic contracts and preserve their PostgreSQL records.

## Functional requirement IDs (all 50)

| ID | Status | Implementation | Actual evidence | Remaining work / scope |
|---|---|---|---|---|
| FR-AUTH-01 | PARTIAL | api/auth.py; security.py; features/Auth.tsx | test_account_login_recovery_settings; live registration/login/logout | Local SMTP authentication/message acceptance and user-confirmed Google dashboard passed; production-domain delivery/recovery still requires qualification. |
| FR-AUTH-02 | COMPLETE | security.py; services/resources.py | test_cross_user_isolation; test_cancellation_and_quota; isolated guest browser | Short-lived guest identity scopes all its limited resources rather than a separate bearer per analysis. |
| FR-AUTH-03 | COMPLETE | services/resources.py; api/* | test_cross_user_isolation; test_expired_source_scope_denies_analysis_derivatives_before_cleanup; test_mcp.py | No claim of independent penetration-test approval. |
| FR-AUTH-04 | PARTIAL | services/resources.py; models.py StorageDeletion; worker.py | test_deletion_rollback_preserves_original_until_committed; test_file_deletion_failure_is_pending_not_false_success | Source deletion returns pending on physical failure. Account deletion response still needs equivalent pending indication; backup/audit retention is operational. |
| FR-ING-01 | COMPLETE | api/documents.py; services/ingest.py; features/Intake.tsx | test_reject_unsafe_or_mismatched_files; live PDF upload; isolated paste/upload | Scans require OCR; no OCR claim. |
| FR-ING-02 | COMPLETE | config.py; services/ingest.py; worker.py | test_size_limit_enforced_before_parser; test_scan_only_pdf_and_encrypted_pdf_rejected; chunk token tests | Reverse proxy must enforce streaming request/body deadlines in deployment. |
| FR-ING-03 | COMPLETE | models.py Source; services/storage.py; worker.py | test_ingest_persistence_original_hash_and_delete; test_source_ids_do_not_collide_for_duplicate_content | Immutable original/version retained; rename changes display title only. |
| FR-ING-04 | COMPLETE | services/ingest.py; services/verification.py | test_text_unicode_identity_offsets; test_docx_preserves_table_and_paragraph_order; PDF coordinate test | PDF viewer displays mapped extracted text, not exact original glyph geometry. |
| FR-ING-05 | COMPLETE | services/ingest.py; worker.py; CoverageNotice.tsx | test_pdf_missing_text_pages_disclosed_and_real_page_coordinates; test_unreadable_pages_never_get_unqualified_supported_status | Detection cannot establish that every meaningful visual element was extracted. |
| FR-ING-06 | COMPLETE | services/chunking.py; models.py Chunk | test_chunking_long_clause_no_loss_and_token_bound; test_oversized_sentence_and_unicode_token_split_preserve_text; test_clauses_not_split_unnecessarily_and_pages_preserved | No fabricated clause/page labels. |
| FR-ING-07 | MISSING | Extraction explicitly rejects scan-only input | test_scan_only_pdf_and_encrypted_pdf_rejected | P1 OCR adapter, confidence and estimated geometry absent. |
| FR-URL-01 | COMPLETE | services/discovery.py | unsafe URL, private DNS, mixed DNS, redirect and pinned-address tests in test_processing.py | Deployment-network SSRF review remains a release gate. |
| FR-URL-02 | PARTIAL | services/discovery.py; api/documents.py | test_discovery_records_missing_inaccessible_and_duplicate_policies; test_sitemap_parsing_is_bounded_and_rejects_entities; live Mozilla discovery | Bounded same-site links/sitemap only; external official locations and JS-rendered navigation not fully supported. |
| FR-URL-03 | PARTIAL | services/discovery.py; features/Intake.tsx | discovery fixture; live 15 candidates/13 accessible | Candidate provenance/status shown; no calibrated discovery confidence score. |
| FR-URL-04 | COMPLETE | services/discovery.py; features/Intake.tsx | discovery missing/inaccessible fixture; live missing-category response | Never guarantees complete legal corpus discovery. |
| FR-URL-05 | COMPLETE | services/discovery.py; worker.py; models.py Source | test_capture_retry_reuses_saved_original_after_extraction_failure; discovery and ingestion tests | Stores available response metadata, bytes/hash and URL provenance. |
| FR-URL-06 | PARTIAL | services/discovery.py; consent schemas | bounded fetch/sitemap tests; robots handling in implementation | No CAPTCHA/login bypass. Exhaustive site-terms assessment is outside automated discovery; deployed-network rate policy needs qualification. |
| FR-URL-07 | PARTIAL | api/comparisons.py; services/comparison.py; features/Compare.tsx | test_comparison.py; isolated account/compare browser | Manual captures and text diffs work; scheduled monitoring, effective-date extraction and alerts absent. |
| FR-AI-01 | COMPLETE | services/analysis.py; schemas.py | test_valid_source_requires_separate_semantic_review; live Gemini/Groq findings | Categories validated by schema; not an accuracy benchmark. |
| FR-AI-02 | COMPLETE | services/analysis.py; models.py Finding/ProviderCall | test_integrated_analysis_reports_qa_delete; duplicate trace test | Records prompt/provider/requested and actual model, source/chunk/candidate metadata. |
| FR-AI-03 | COMPLETE | services/analysis.py prompts; provider schemas | test_question_answer_requires_semantic_support; live scoped Q&A | No external legal research mode enabled. |
| FR-AI-04 | COMPLETE | services/verification.py; worker.py | test_forged_citations_never_verified; test_false_citations_never_valid; repeated-quote test | Worker revalidates citations before persistence. |
| FR-AI-05 | PARTIAL | services/analysis.py semantic verifier | test_quote_match_does_not_entail_statement; test_semantic_failure_is_visible_ambiguous; live Gemini/Groq | Separate review works; human-labeled semantic accuracy/calibration not established. |
| FR-AI-06 | COMPLETE | services/verification.py; lib/evidence.ts; Workspace.tsx | test_exact_quote_is_not_semantic_support; frontend evidence tests; workspace browser | Invalid locations never receive verified label/highlight. |
| FR-AI-07 | COMPLETE | services/analysis.py; Workspace.tsx | forged/ambiguous backend tests; workspace invalid citation browser | Rejected candidates remain visible with explanations. |
| FR-AI-08 | COMPLETE | services/analysis.py aggregation | test_duplicate_findings_preserve_candidate_trace | Normalized duplicate removal preserves original candidates; no semantic conflict claim. |
| FR-AI-09 | PARTIAL | services/analysis.py global context review | test_missing_exception_downgrades_supported_verdict; test_semantic_review_receives_distant_exception; context-limit test | Bounded global context; ambiguity when complete context cannot fit. Missing appendix detection is model-dependent. |
| FR-AI-10 | COMPLETE | worker.py; services/analysis.py; CoverageNotice.tsx | test_partial_generation_reports_uncovered_chunks_and_sections; unreadable-page test | Discrete actual stages/counts; no artificial progress percentage. |
| FR-AI-11 | PARTIAL | providers/*; services/analysis.py; config.py | adapter/retry/consent tests; three live probes; Gemini/Groq full pipeline | OpenRouter full schema returned429. Separate role-model UI, hard spend ceiling and per-call resume incomplete. |
| FR-AI-12 | COMPLETE | providers/base.py; models.py ProviderCall | test_adapters_normalize_structured_outputs; live token/latency metadata | Pricing estimates only when configured; no guarantee of free service. |
| FR-AI-13 | COMPLETE | schemas.py; lib/evidence.ts; Evidence Passport | frontend evidence tests; live Passport | Qualitative support explanations; no fabricated confidence percentage. |
| FR-AI-14 | COMPLETE | services/analysis.py | test_no_supported_evidence_abstains_without_provider_call; test_question_answer_with_forged_citation_abstains | Abstention distinguishes missing evidence from absence of a provision. |
| FR-AI-15 | MISSING | Text comparison is not semantic conflict detection | test_comparison.py covers text only | P1 cross-document conflict verifier absent. |
| FR-AI-16 | MISSING | No active review route | Not tested; absent on inspection | P1 expert approve/reject/rewrite and immutable review history absent. |
| FR-QA-01 | COMPLETE | services/retrieval.py; services/analysis.py; api/analyses.py; QuestionPanel.tsx | test_source_question_can_use_verified_evidence_without_prior_findings; PostgreSQL native retrieval test; live Q&A/citation navigation | Answer sources not restricted to prior findings. |
| FR-QA-02 | COMPLETE | services/analysis.py; QuestionPanel.tsx | forged answer/semantic failure tests; isolated workspace abstention browser | No invented missing terms. |
| FR-QA-03 | PARTIAL | services/analysis.py answer semantic review | test_question_answer_requires_semantic_support; exception tests | Conservative context cap; human exception/contradiction benchmark pending. |
| FR-QA-04 | COMPLETE | models.py Conversation; api/analyses.py; QuestionPanel.tsx | test_integrated_analysis_reports_qa_delete; live refresh/history | Registered conversations retained; guest UI cache is transient. |
| FR-UI-01 | PARTIAL | SourceViewer.tsx; Workspace.tsx | live PDF evidence highlight; workspace invalid-location browser | Exact retained-text highlights and real page anchors work; original PDF geometry overlay absent. |
| FR-UI-02 | COMPLETE | api/analyses.py; Workspace.tsx; lib/query.ts | integrated API tests; navigation unit tests; workspace browser | Server filters/pagination; category/status/source/query in URL. |
| FR-UI-03 | COMPLETE | api/dashboard.py; features/Dashboard.tsx; Library.tsx | test_dashboard_pagination_and_display_only_rename; live dashboard/library | Real counts/activity only. |
| FR-UI-04 | PARTIAL | worker.py; SourcePage.tsx; Workspace.tsx; ui.tsx | cancellation/expired lease/retry tests; core browser | Core state paths tested; not every provider/browser interruption combination exhaustively verified. |
| FR-UI-05 | PARTIAL | Tabs.tsx; SourceViewer.tsx; styles.css | navigation.test.tsx; 320px/mobile browsers; axe public pages | Full screen-reader, keyboard-only journey, tablet and200% zoom audit pending. |
| FR-EXP-01 | COMPLETE | api/analyses.py; services/reports.py; models.py Report | test_integrated_analysis_reports_qa_delete; live PDF download | Encrypted report retained with DB metadata; not legal certification. |
| FR-EXP-02 | COMPLETE | services/reports.py; api/analyses.py | integrated manifest hash assertion; live JSON download | Source IDs/hashes/coordinates/provider and limitation metadata included. |
| FR-EXP-03 | COMPLETE | api/documents.py; services/resources.py | test_cross_user_isolation; original hash test; URL original-download restriction | Third-party captured originals not redistributable through download endpoint. |
| FR-EXP-04 | PARTIAL | services/resources.py; StorageDeletion; worker.py | test_delete_source_removes_derived_analysis_findings_and_original; rollback/outbox tests | Source/account cascade implemented; standalone analysis-deletion UI/API absent. Physical cleanup failures queue retries. |
| FR-EXP-05 | MISSING | Hashes/capture dates are not trusted timestamps | No trusted timestamp test; absent on inspection | P1 signed/timed evidence bundle and chain-of-custody process absent. |
| FR-CMP-01 | PARTIAL | services/comparison.py; api/comparisons.py; features/Compare.tsx | test_comparison.py; isolated compare browser | Aligned retained-text diff works; semantic alignment and effective/observed chronology incomplete. |
| FR-REV-01 | MISSING | No reviewer feature enabled | Absent on inspection | P1 reviewer identity/sign-off/audited decisions absent. |

## Architecture and product decisions

| ID | Status | Code / exercised evidence | Remaining work |
|---|---|---|---|
| ADR-01 | COMPLETE | frontend/package.json, src/app/App.tsx; TypeScript/build and browser tests | None for chosen stack. |
| ADR-02 | PARTIAL | Lucide, ui.tsx, Tabs.tsx; axe and tab unit tests | Complete manual accessibility qualification. |
| ADR-03 | COMPLETE | backend/pyproject.toml, app/main.py, schemas.py;118 backend tests | No stack gap. |
| ADR-04 | COMPLETE | db.py, models.py, migrations/; live PostgreSQL18, four upgrades, alembic check, native FTS/FK integration | Backup restore qualification separate. |
| ADR-05 | PARTIAL | worker.py; cancellation/lease/retry tests; real worker processed PDF | Two-worker contention/load qualification and per-call checkpointing pending. |
| ADR-06 | PARTIAL | storage.py; encrypted filesystem/report tests and SDK-mocked S3 tests | Encrypted S3 adapter implemented; remote bucket/IAM/lifecycle qualification pending. |
| ADR-07 | PARTIAL | providers/*; all three live simple probes, Gemini/Groq full schema | OpenRouter full schema blocked by429. |
| ADR-08 | PARTIAL | retrieval.py; native PostgreSQL FTS/ownership rollback integration | GIN optimization and measured recall benchmark pending. |
| ADR-09 | PARTIAL | ingest.py, verification.py; format/offset tests and live PDF highlight | Retained-text navigation implemented; original PDF geometry UI incomplete. |
| ADR-10 | PARTIAL | mcp_server.py, tests/test_mcp.py | Private scoped read-only adapter only; production OAuth/client interoperability qualification absent. |
| ADR-11 | PARTIAL | /api/v1, schemas.py, docs/openapi.json; snapshot test | Remaining untyped message/export dictionaries and SDK contract generation can improve. |
| ADR-12 | PARTIAL | security.py, resources.py, discovery.py; ownership/SSRF/CSRF tests | Independent review, parser sandbox, deployed least privilege and operational tests pending. |
| DEC-01 | COMPLETE | Document-only prompts/copy and explicit disclaimers; semantic negative tests | No governing-law opinions enabled. |
| DEC-02 | COMPLETE | FastAPI/PostgreSQL/dedicated worker; live full browser flow | None for selected architecture. |
| DEC-03 | PARTIAL | Configured provider adapters, consent and telemetry | OpenRouter quota and current deployment privacy terms require qualification. |
| DEC-04 | PARTIAL | Encrypted filesystem development adapter and S3 production adapter | Remote private bucket/IAM/retention validation pending. |
| DEC-05 | COMPLETE | Guest issuance/quota/expiry and account upgrade tests | Public deployment abuse controls require qualification. |
| DEC-06 | COMPLETE | Scanned PDF rejection/coverage tests; OCR explicitly deferred | P1 OCR remains missing, as decided. |
| DEC-07 | PARTIAL | Shared REST authorization and private MCP tests | P1 public authorized MCP integration not released. |
| DEC-08 | COMPLETE | Current accessible snapshots retained; discovery tests | P1 historical archive/change monitoring not claimed. |
| DEC-09 | COMPLETE | Live PDF/JSON downloads; ownership/license original restriction; retained report roundtrip | No admissibility claim. |

## Acceptance scenarios

| ID | Status | Executed evidence / gap |
|---|---|---|
| AT-01 | PARTIAL | DOCX paragraph/table extraction and source validation tests pass; live numbered-DOCX AI browser scenario not executed. |
| AT-02 | COMPLETE | Parameterized forged page/offset/source tests and invalid-location browser scenario pass. |
| AT-03 | COMPLETE | Missing-exception downgrade and distant-exception semantic fixtures pass; not a human accuracy benchmark. |
| AT-04 | COMPLETE | Discovery fixture records403/inaccessible and missing categories. |
| AT-05 | PARTIAL | HTML passive extraction test passes; prompts delimit untrusted text, no execution tools exposed. Adversarial model benchmark pending. |
| AT-06 | COMPLETE | Cross-user/session isolation tests pass. |
| AT-07 | COMPLETE | Deletion/cascade/outbox rollback and pending-failure tests pass; isolated browser deletes only synthetic test data. |
| AT-08 | COMPLETE | Partial generation fixture identifies uncovered chunks after provider failure; actual OpenRouter429 classified without replacement. |
| AT-09 | COMPLETE | Duplicate findings preserve original candidate trace in test_ai.py. |
| AT-10 | PARTIAL | Unsupported and forged-answer abstention tests pass; exact retention-period natural-language fixture/human evaluation pending. |
| AT-11 | PARTIAL | Global context and missing-exception controls tested; dedicated missing-appendix corpus not evaluated. |
| AT-12 | COMPLETE | Partial semantic state/explanation and frontend status mapping tests pass. |
| AT-13 | COMPLETE | Integrated manifest source hash assertion and live manifest download pass. |
| AT-14 | PARTIAL | Tab roving keyboard test and semantic buttons pass; complete mouse-free evidence journey not manually qualified. |
| AT-15 | COMPLETE | Scan-only PDF is rejected with OCR-required notice; no invented empty analysis. |

## Design packages and release milestones

| ID | Status | Evidence and remaining work |
|---|---|---|
| DS-01 | PARTIAL | Central neutral/teal tokens, Lucide, common dialogs/tabs, public axe checks; all-page manual contrast/focus audit pending. |
| DS-02 | PARTIAL | Live PDF upload and policy discovery; isolated text/guest/error flows; exhaustive input/browser matrix pending. |
| DS-03 | PARTIAL | Real split workspace, exact retained-text highlights, Passport, server filters, coverage; original PDF overlay/complete zoom controls absent. |
| DS-04 | COMPLETE | Live scoped Q&A, source navigation, refresh history, reports, dashboard/library and persisted settings; encrypted retained report integration passes. |
| DS-05 | PARTIAL | Automated axe on three public pages and320px/mobile browser checks pass; screen-reader,200% zoom, tablet and full keyboard manual audit pending. |
| G0 | PARTIAL | All four baseline documents transcribed/read and traced here; named product/design/security sign-off not supplied. |
| G1 | PARTIAL | PostgreSQL schema/migrations, encrypted originals, mapped chunks and durable jobs tested; production recovery/load gate pending. |
| G2 | PARTIAL | Live Gemini/Groq and deterministic/semantic safety fixtures pass; OpenRouter quota and independent labeled evaluation block verified-AI release qualification. |
| G3 | PARTIAL | Core application workflows run live and regressions pass; remaining FR partials above prevent blanket acceptance. |
| G4 | PARTIAL | Security negative tests, lint/build/axe and safe migration checks pass; SMTP, restore drills, independent security/accessibility/operations approval pending. |
| G5 | PARTIAL | Text comparison/private MCP implemented; OCR, expert review, semantic conflicts, trusted timestamps and monitoring absent. |

## Requirements without canonical IDs

PRD scope/non-functional goals, FRD sections7/9 and TRD operational/testing sections are covered as follows: durable stages/cancel/retry and provenance are tested; retry cannot promise free replay. English document-only interpretation is the supported scope. Pricing is optional estimated telemetry, not an enforceable spending cap. Latency/load/quality targets lack a representative benchmark. Database/volume encryption, backup retention, restore drills, deployed monitoring/alerting, production email and least-privilege infrastructure remain operator/release work. Settings expose actual retention/provider behavior; no pretend preferences or fabricated analytics are enabled. Original PDF rendering, trusted human review and the full manual WCAG2.2 AA journey remain incomplete.

No critical failure reproduced in the exercised core path remains open. This is not a claim that every requirement is complete or that production security/evidence accuracy has been certified. OpenRouter's full-schema429 is the current reproduced external dependency failure. No existing user documents were deleted to make tests pass.

## 10 November 2026 feature acceptance amendment

This section supersedes earlier descriptions of local-development email activation and English-only output. The original50-ID baseline remains traceable above; new contracts are in the FRD amendment.

| ID | Status | Implementation | Actual evidence / blocker |
|---|---|---|---|
| FR-AUTH-05 | PARTIAL | services/identity.py; api/auth.py Google start/callback/link; OAuthAttempt/OAuthIdentity; Auth.tsx/Settings.tsx | Local RSA-signed JWT issuer/audience/expiry/nonce/email tests and state/PKCE/single-use/no-email-autolink integration pass. Google credentials missing; live consent/callback not exercised. |
| FR-AUTH-06 | COMPLETE within isolated acceptance | PendingRegistration; auth register/verify; identity mail transport; dedicated frontend routes | Pending user absent until verification, chosen-password check, expiry, replay, guest upgrade and real-token browser journey pass. Local SMTP authentication/message acceptance passed; inbox placement and production delivery remain unverified. No dev/prod activation bypass. |
| FR-AUTH-07 | PARTIAL | AuthToken; recover/reset; TLS mail; shared sessions; forgot/reset routes | Single-use reset, old-session invalidation, old-password rejection, anti-enumeration and isolated browser email-link/reset/login pass. Actual production mailbox delivery requires qualification. |
| FR-SUM-01 | COMPLETE within tested scope | services/summary.py; summary API; SmartSummary/Workspace/SourceViewer | Validated quote/page tests; all-language summary unit/browser source navigation passes. Original detailed results/reports regression remains intact. |
| FR-SUM-02 | COMPLETE within documented rules | attention-1.0, conservative coverage/verification gate and explicit rule explanation | High/Moderate/Low/Not Determinable, positive/negated trigger and invalid page tests pass. Limited English phrase rules are document attention, not a validated general legal-risk model. |
| FR-LANG-01 | COMPLETE within implementation tests | users.language; AccountInput; LanguageSelect; translated finding/Passport overlays | Three-language selectors, preference persistence, invalid-language422, original-quote preservation and navigation pass. Workspace override is transient; Account default persists. |
| FR-LANG-02 | PARTIAL | LocalizedAnalysis; localization.py; POST translations/cache; GET summary | Strict IDs, separate fidelity rejection, cache/ownership integration pass. Live Groq Hindi/Hinglish translation passed. Large corpora/human translation-quality benchmark pending. |
| FR-LANG-03 | PARTIAL | multilingual retrieval normalization; ask directive/semantic validation; Question.answer language; QuestionPanel | All-language grounding/abstention fixtures pass. Live Groq English answer cited original text. Hindi/Hinglish live answers blocked by429; Gemini smoke unavailable/rate-limited. No silent fallback. |

Migration `dfda9673d7bc` applied on configured PostgreSQL; alembic check reports no drift. `backend/.env` still matches its prior fingerprint. Updated external setup instructions are in HOW_TO_RUN. Production readiness is not claimed: production-domain Google/SMTP qualification, provider quotas and independent semantic/linguistic/accessibility/security evaluations remain explicit release blockers.

## Current feature request — Summary UI, global language and email-first signup

This section supersedes older descriptions of an analysis-local language selector and password-before-verification signup. It preserves previous API contracts and historical test evidence above.

| ID | Status | Implementation | Executed evidence / limitation |
|---|---|---|---|
| FR-AUTH-08 | COMPLETE in isolated integration | auth registration/start, verify, complete; PendingRegistration.verified_at; Auth.tsx step flow | Email-only first form; no user/password before ownership; rotated email/setup digests;15-minute confirmed-password step; replay/expiry tests; real-token Playwright registration/login/reset passes. Live SMTP TLS/auth and self-addressed message acceptance passed. Inbox placement is not claimed. |
| FR-LANG-04 | COMPLETE in tested routes | app/language.tsx; header globe; PATCH /me/language | Cross-page navigation, real guest database persistence, reload, HTML language and zero-AI-request browser scenario passed. Preference writes serialize in selection order; CSRF and invalid-language tests passed. |
| FR-LANG-05 | COMPLETE within supported cache budgets | messages.json, ui-keys.json, useLanguage in feature/shared components; fingerprinted explanation preparation | All wired static keys have Hindi/Hinglish entries; unit coverage passes. Saved analysis explanation cache/ownership and exact-quote tests pass. Provider failure explicitly keeps originals rather than claiming translated output. Full human linguistic audit remains pending. |
| FR-UI-06 | COMPLETE within automated/visual scope | SmartSummary.tsx/styles.css/Workspace.tsx | Risk/category/warning hierarchy, unique clause count, preserved toggle and citations checked by browser tests; desktop screenshot visually inspected. Mobile320/375px regressions passed. |
| FR-EXP-06 | COMPLETE within integration | analyses exports language query; reports.py; existing LocalizedAnalysis | Cached Hindi/Hinglish JSON/PDF exports passed, preserving original quotes/explanations and all coverage/limitation metadata; report generation makes no new AI translation call. |
| FR-AUTH-05 current live status | PARTIAL live acceptance | Existing Google state/nonce/PKCE/JWT/linking implementation retained | Google is configured and authorization page returns200. Signature, state, reuse and no-auto-link tests pass; actual user-approved consent/callback needs interactive browser completion. |

Database revision0f439d83280f is a single nullable timestamp addition; applied on existing PostgreSQL without resets/deletion. Current .env remains byte-for-byte unchanged during this request. Automated acceptance is not a claim of full manual WCAG/linguistic/security or production certification.


## Final UI and production preparation (2026-11-10)

The following extension IDs supplement the baseline rather than renumbering original requirements. Earlier test totals are historical; the latest execution is in VERIFICATION.md. No database reset or production deployment was performed.

| Extension ID | Status | Code location | Executed evidence | Remaining work |
|---|---|---|---|---|
| UI-FINAL-01 | COMPLETE within browser scope | Workspace.tsx | workspace.spec.ts: Summary selected initially and after reload; Detailed tab remains accessible | Human usability review |
| UI-FINAL-02 | COMPLETE within browser scope | Workspace.tsx; styles.css | workspace.spec.ts: coverage hidden in Summary, below detailed grid | Full keyboard/screen-reader audit |
| UI-FINAL-03 | COMPLETE within automated scope | SmartSummary.tsx | SmartSummary.test.tsx; localized browser quote/citation flow | Independent language/evidence benchmark |
| UI-FINAL-04 | COMPLETE within browser scope | styles.css; App.tsx | core.spec.ts mobile upload/delete/logout; responsive landing | Broader device matrix |
| BRAND-01 | COMPLETE within automated scope | BrandMark.tsx; App.tsx | BrandMark.test.tsx load/error; branding.spec.ts missing-image/footer/mobile | Existing user-supplied logo preserved; final asset can replace it |
| CHAT-SUGGEST-01 | COMPLETE within unit scope | summary.py; analyses.py; QuestionPanel.tsx | test_suggested_questions_require_actual_supported_categories, all three languages | Human question-quality review |
| OPS-STORAGE-01 | PARTIAL | storage.py; config.py | SDK-mocked encrypted roundtrip/no local file; conditional PUT; retryable deletion failure; invalid identifier rejection | Actual private bucket/IAM/retention qualification |
| OPS-RESET-01 | COMPLETE for preparation; NOT EXECUTED | reset_documents.py; DATABASE_RESET.md | Production refusal/missing-backup/missing-approval tests; real PG read-only plan | Separate approval and verified backup needed before any development/staging deletion |
| OPS-DEPLOY-01 | PARTIAL | backend/Dockerfile; runtime lock; prepare_vercel.py; vercel.example.json | Generator API-before-SPA and localhost-rejection tests; frontend production build | Docker unavailable locally; real domains/hosting and staging validation required |
| OPS-OAUTH-01 | PARTIAL for production | auth.py; config.py | OAuth regression/browser session/replay; explicit proxy-host allowlist test; earlier user-confirmed local Google dashboard | Production-domain Google consent, trusted ingress and SMTP delivery |

Confirmed unused LanguageSelect.tsx was removed after repository-wide reference checks. The tracked TypeScript incremental cache was removed from source control inputs; future generated copies are ignored. No meaningful tests or migrations were deleted. Deployment packaging excludes tests, tools, caches and local secrets. Runtime documents/private files were preserved.


## Cleanup and hardcoding review (10 November 2026)

| Extension | Status | Code / verification | Scope |
|---|---|---|---|
| UI-CLEAN-01 | COMPLETE within browser acceptance | App.tsx/styles.css; branding.spec.ts | Dot-free wordmarks; visible keyboard focus and active navigation; reduced-motion and mobile width checks |
| UI-CLEAN-02 | COMPLETE within regression scope | SmartSummary/QuestionPanel/SourceViewer/Compare/Workspace; unit and workspace browser tests | Collapsed reading guidance, neutral localized question prompt and translated page labels; exact evidence unchanged |
| CONFIG-CLEAN-01 | COMPLETE within configuration scope | vite.config.ts; config.py; production guard tests | Environment-file proxy loading and process override checked with temporary synthetic env; production loopback endpoint rejection |
| CLEAN-SAFE-01 | COMPLETE for this review scope | Source/reference/dependency/deploy inventory; Ruff; unused TypeScript checks | No unproven source/dependency deletion; tests/migrations/security/docs retained; PostgreSQL unchanged |

Hardcoding review found no credential-pattern matches in scanned application/maintenance source. This is a scoped pattern check, not an independent secret-scanning certification. Legitimate constants retained: provider protocol endpoints, Google issuer/JWKS/token trust anchors, enums/validation/risk rules, localization catalogs, non-production localhost defaults, documented deployment examples and synthetic test/CI data. No production mock findings or sample-user responses were introduced. The generated TypeScript incremental cache is removed after verification and remains ignored; no source file removal was justified in this pass.


## Latest authentication / mobile deployment regression

FR-AUTH-01/05..08 remain implemented with isolated signup/login/reset/OIDC acceptance. First-party Vercel proxy configuration is prepared to eliminate the Vercel/Render third-party-cookie dependency; optional None cookies require Secure and keep Origin/CSRF checks. Auth now requires confirmed session restoration before dashboard navigation, redirects anonymous private pages to sign-in, and handles logout/expired sessions without retaining private caches. HTML OAuth errors clear transient cookies and remove callback parameters; API replay remains400. Incorrect trusted HTTPS ingress fails closed instead of redirecting endlessly. Final verification:197 backend tests passed,1 skipped;23 frontend tests passed;15 browser scenarios passed,1 skipped; lint/build passed. Actual production mobile consent/mail/session acceptance remains PARTIAL pending manual deployment and live verification. See VERIFICATION.md/DEPLOYMENT.md; no new database migrations or .env changes.
