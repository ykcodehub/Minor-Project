# College demo readiness — 11 November 2026

**Offline synthetic demonstration: PASS. Live AI end-to-end acceptance: FAIL.** This is a local result, not a production-readiness or legal-accuracy certification. No commits, pushes, deployments, secret changes or production-data writes were performed.

## Run the working demonstration

The production frontend preview is available locally at **http://127.0.0.1:5180/demo/offline**. To start it again:

```powershell
cd frontend
npm run build
npm run preview -- --port 5180 --strictPort
```

This route needs the local frontend server, but no internet, backend, database, credentials or AI provider. It is not a service-worker/PWA installation and an uncached deployed page still needs its frontend assets downloaded. The persistent banner says **Offline demo — authored reference, not live AI**. It is never substituted for a private upload, analysis job or failed live answer.

The public two-page synthetic PDF has seven authored reference annotations, exact original quotations/offsets/pages, transparent High/Moderate/Low rules, Summary and Detailed Analysis, source navigation, a hash, PDF/reference downloads and English/Hindi/Hinglish explanations. Saved QA supports one clearly labeled payment question in those languages; unknown questions abstain. It is not generative chat. The seven reference annotations were source-checked locally; they were not independently verified by a live model or certified by a legal reviewer.

## Workflow results

| Workflow | Local/offline evidence | Real-provider outcome |
|---|---|---|
| Authentication, session isolation, OAuth desktop/mobile | PASS: existing backend/browser regressions, synthetic Google callback | Real Google consent not repeated |
| Upload/extraction/history/reports | PASS: isolated API/browser regressions; exact two-page mapping | Live evaluation used synthetic PDF extraction and isolated SQLAlchemy persistence |
| PostgreSQL | PASS: read-only connection; head `c819ba204ae1` matches local migrations; 3 evidence foreign keys | No production mutation/integration test was run |
| Candidate generation | PASS: local regression and authored demo | Returned 7 findings on the 36-block fixture, 6 on the compact fixture; semantic correctness not established |
| Context indexing | PASS: local regression | Initial FAIL from invalid model-provided offsets; compact post-fix PASS, 1/1 source window validated |
| Exact evidence quotes/pages | PASS | Initial 7/7 and compact 6/6 retained citations source-matched EXACT; both PDFs retained 2 original pages |
| Semantic verification | PASS: safeguards/regressions | FAIL: compact run had 5 AMBIGUOUS and 1 PARTIALLY_SUPPORTED findings; 0 SUPPORTED |
| Summary/Risk Dashboard | PASS: authored reference; replay of real partial result stays honest | FAIL meaningful verified-result acceptance; correctly displays Not Determinable and no fabricated risk distribution |
| Detailed Analysis | PASS: filtering, original evidence and source navigation | Real findings retained with unverified statuses, not promoted |
| Translation | PASS: authored offline Hindi/Hinglish and existing mocked caching/fidelity tests | BLOCKED: no supported live findings available to translate |
| Ask Veriora | PASS: saved offline answer, unknown-question abstention and existing grounded-QA regressions | FAIL: live draft returned, semantic answer verification abstained (`ANSWER_NOT_VERIFIED`) |
| Production frontend build | PASS: TypeScript + Vite, offline route included | Does not certify live providers |

## Actual controlled live measurements

Only `dots-studio/dots-3-note-preview:free` via **AtlasCloud** received synthetic content, after explicit model-specific approval. Catalog and endpoint input/output prices were zero; endpoint status was 0 with positive recent uptime; structured output, optional reasoning and token controls were advertised. Requests pinned the selected endpoint with `allow_fallbacks=false`, `require_parameters=true` and a zero prompt/completion/request price ceiling. Adapter retries and output-recovery subdivision were disabled. No provider/model switch occurred.

| Measurement | Existing benchmark fixture | Compact authored fixture |
|---|---:|---:|
| PDF pages / extracted blocks | 2 / 36 | 2 / 9 |
| Wall seconds | 50.131 | 69.481 |
| Actual outbound inference requests | 5 | 10 |
| Estimated input + reserved completion tokens | 37,898 | 39,122 |
| Reported prompt tokens | 16,692 | 9,701 |
| Reported completion tokens | 1,204 | 1,534 |
| Reported reasoning tokens | 0 | 0 |
| HTTP outcomes | five 200 | nine 200, one 400 |
| Reported cost | 0 on all five responses | 0 on nine responses; 400 supplied no usage/cost |
| Fully supported findings | 0/7 | 0/6 |

**Cumulative: 15/20 requests and 77,020/80,000 reserved estimated tokens.** Reported actual tokens total 26,393 input + 2,738 completion, excluding the HTTP 400 whose usage was not supplied. No unknown usage is represented as measured zero. The zero-price route/ceiling was enforced on every request. Further inference was stopped; the remaining reserved-token allowance cannot fund a complete repeat. Raw sanitized evidence: [initial run](benchmarks/college_live.json), [compact run](benchmarks/college_live_compact.json), [totals](benchmarks/college_live_totals.json).

The compact fixture is a separate shorter-text two-page agreement, not a performance optimization that removed text from the original 36-block agreement. It preserves the same seven substantive reference clauses, but it is not the same benchmark document. The model returned only six, including a license clause classified as RIGHT. Exact citation matching therefore must not be confused with complete clause detection, sound categorization or semantic accuracy.

## Confirmed issues and local fixes

1. **Index offsets:** the first source-index response guessed incorrect end offsets despite valid JSON. Validation rejected it. The indexing prompt now requests null offsets and preserves strict unique-quotation resolution; invalid explicit offsets still fail. The subsequent compact run validated its source window.
2. **Repeated failed indexing:** separate index instances in analysis and QA could re-request the same failed window. Operation-scoped index records now reuse the exact source/provider/model result, including honest incomplete coverage. Checkpoints and tenant consent are preserved.
3. **Task/model health:** explicit OpenRouter requests now require a currently healthy structured-output endpoint; free variants also require zero endpoint pricing and carry a server-side zero-price ceiling. Endpoint selection is pinned, with a short metadata cache; it is still not a guarantee of inference success.
4. **Candidate limits and semantics:** the live model miscategorized clauses, invented references and treated absent external definitions as missing source support. Prompt instructions now distinguish actual document references from map aliases, document statements from enforceability/practices, and remove the arbitrary six-finding instruction while retaining schema/output/operation bounds. The final rubric/candidate refinements passed local regressions but were **not live-retested** after the approved token budget was nearly consumed. No old verdict was relabeled.
5. **Controlled-test harness:** its first version mislabeled a 400 without usage as `ZERO_COST_RESPONSE_UNCONFIRMED`, and normal partial-result recovery continued later stages. This was a harness defect, not proof that the provider charged money. The final harness treats HTTP errors separately, captures sanitized provider diagnostics and uses an exception that aborts the entire run on HTTP, transport, health or cost uncertainty. Regression tests prove the adapter cannot catch it and retry. The original 400 body was not retained, so its precise upstream validation message remains unknown. **No new inference was executed after this guard correction.**

## Existing and alternative provider assessment

- Gemini `gemini-3.6-flash`: authenticated model-list GET 200, model listed with GenerateContent support. Groq `openai/gpt-oss-20b`: GET 200, model listed and active. These are metadata checks, not inference or quota-health proofs. Account-specific free billing/quota eligibility was not established, so neither received inference content. Both remain usable only under existing user consent and configured policies. [Metadata evidence](benchmarks/provider_metadata_readiness.json).
- NVIDIA `nvidia/nemotron-3.5-super-vl:free`: public endpoint status -5 and recent uptime 0 at the initial check; not used. Dots was separately authorized, tested, and failed the full acceptance criteria. Dots Preview is scheduled to retire on 31 December 2026.
- No additional provider was silently authorized. No additional approved credentials or verified zero-spend account were available. No local inference runtime/model was installed, and no local model was memory-qualified for Render Free's 512 MB service. Adding an untested adapter/runtime would not establish reliability; none was installed.

## Deployment and remaining release gates

No production settings were changed. Existing backend deployment remains FastAPI plus the supervised worker via `python -m app.serve`; API and worker must share Neon, stable encryption settings and persistent R2 storage. Existing CORS, HTTPS cookies, OAuth callbacks and SMTP configuration remain required. There is no new database migration or need to reset data.

For the offline demonstration, build/deploy the frontend through the existing approved Vercel workflow only after separate deployment authorization. The PDF is public synthetic material; no secrets are bundled. For live analysis, `OPENROUTER_MODEL=openrouter/free` must eventually be replaced by a deliberately selected explicit model, but **do not treat the failed Dots run as a recommendation for production deployment**. No model environment value was changed here.

Remaining gates: approved account-specific zero-spend testing for a higher-quality configured provider, a new bounded evaluation budget before further inference, real semantic/categorization/QA quality, full live multilingual translation and production Render/Vercel verification. Human review is still required for legal interpretation. Readiness/metadata HTTP 200 is not an AI-health or accuracy certificate.

## Executed checks

- Backend: **314 passed, 1 skipped**, 138.48 seconds. `python -m pytest tests -q --tb=short`, with test-only SQLite and inherited live keys disabled. Opt-in mutating PostgreSQL integration was skipped.
- Frontend: **56 unit tests passed**; ESLint, TypeScript and production Vite build passed.
- Browser main suite: **31 passed, 1 skipped**, about 1.6 minutes. Includes synthetic auth/OAuth, uploads, histories/reports, language, risk/evidence navigation and desktop/mobile offline mode with API access blocked. No real Google consent or production mutation was performed.
- Recorded real Dots partial-response browser replay: **1 passed**. This is a recorded-response integration test, not fresh browser-to-provider inference.
- Ruff and targeted Python formatting passed. Existing meaningful tests/migrations were preserved.
- PostgreSQL connection/migration-head/foreign-key checks passed inside a read-only transaction. [Evidence](benchmarks/demo_postgres_readonly.json).

See [verification history](VERIFICATION.md) and [offline fixture validation](../backend/tests/test_offline_demo.py). The reliable college presentation path is the explicitly labeled offline reference; live end-to-end AI is not ready to promise.

- Production-build preview validation: **2 passed**, desktop/mobile offline tests against http://127.0.0.1:5180 with API requests blocked, 10.2 seconds. This repeats the offline scenarios against built assets; it is not two additional live-provider cases.
