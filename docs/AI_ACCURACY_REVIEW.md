# Live accuracy follow-up: recorded-response diagnosis

This follow-up used existing synthetic recordings first. **No new inference request was made.** Historical results, source files, private `.env`, migrations and production records were not rewritten. The offline authored demo remains separate from live analysis.

## Exact status path

1. `services/analysis.py:CandidateBatch` validates candidate JSON, then `_validated_citation` checks the authorized source, section, page, exact/normalized quote and original offsets. Invalid evidence cannot become supported.
2. `services/context_index.py:SourceWideIndex.prepare` reviews all qualification windows and source-validates every returned excerpt. An incomplete index blocks that indexed verification path.
3. `SourceWideIndex.review` passes whole source when small enough, otherwise validated indexed context plus bounded evidence/reference passages, to `_review_context`.
4. `_review_context` validates the structured categorical verdict. SUPPORTED with missing qualifiers/references is downgraded; incomplete context prevents full support. New integrity guards reject invented unresolved map references and explicitly inconsistent categories, allowing only another already-authorized reviewer to evaluate the claim.
5. `analyze` retains failures as unverified findings with reason codes. `summary.summarize` includes only supported, source-valid findings. Unknown or incomplete scope stays Not Determinable; supported facts can still be displayed when other findings require review.

**There is no numerical confidence calculation or percentage threshold in this path.** Replacing a confidence cutoff cannot fix these recordings. Exact quote validation establishes provenance, not semantic correctness, category accuracy, legal completeness or actual company behavior.

## First recording: seven candidates, zero semantic decisions

[college_live.json](benchmarks/college_live.json) used the two-page/36-block benchmark. All seven retained citations matched EXACT with correct pages. The first context audit returned schema-valid JSON but guessed wrong numeric end offsets. Index validation failed (`PROVIDER_INVALID_OUTPUT`); 0/3 windows were validated and every candidate became AMBIGUOUS without a semantic-verification call. Thus this run does not demonstrate seven negative semantic judgments.

| Candidate quote/topic | Recorded category | Final rejection |
|---|---|---|
| Data sharing only with consent | CONSENT | Index citation failure; no semantic review |
| Irrevocable license | CONSENT | Same index failure; category also poorly matched |
| Unlimited liability | CONSENT | Same index failure; category also poorly matched |
| Thirty-day invoice payment | CONSENT | Same index failure; category also poorly matched |
| Seven-day termination | TERMINATION | Same index failure; generated references were map aliases |
| Arbitration/stated venue | DISPUTE | Same index failure; generated references were map aliases |
| Copy of stored records | RESTRICTION | Same index failure; entitlement mislabeled and map references generated |

The earlier implementation already corrected the index prompt to use null offsets with unique exact-quote resolution and shared per-operation index state. Those fixes were preserved, not reapplied or represented as newly verified inference.

## Compact recording: actual per-candidate reasons

[college_live_compact.json](benchmarks/college_live_compact.json) used a **different**, compact two-page/nine-block synthetic agreement. Its index passed; retained evidence was EXACT, and semantic context was marked complete. HTTP 200/schema acceptance did not establish sound review reasoning.

| Candidate | Recorded result | Exact rejection basis and interpretation |
|---|---|---|
| Unlimited liability, page 1 | AMBIGUOUS | Reviewer demanded definitions of service losses, a liability cap, exclusions and mutual duties. These are unstated safeguards, not necessarily qualifications required to report that the document contains the quoted term. Model/prompt-scope problem; not grounds for automatic promotion. |
| Irrevocable license, page 1 | PARTIALLY_SUPPORTED | Reviewer demanded scope, termination, consent and venue terms and reported `sec_122d4d2a8938_4` and `sec_122d4d2a8938_7` as unresolved references. These are parser IDs, not written clause references. Candidate was also mislabeled RIGHT. |
| Thirty-day payment, page 1 | AMBIGUOUS | Real HTTP 400 during review. The earlier harness mislabeled its absent error-response usage as `ZERO_COST_RESPONSE_UNCONFIRMED`. The original error body was not retained, so a specific upstream schema/parameter cause cannot be confirmed. |
| Consent-limited sharing, page 1 | AMBIGUOUS | Reviewer demanded a consent definition, provider scope and legal-obligation exceptions not supplied by this document. No numerical threshold or evidence-location failure occurred. |
| Seven-day termination, page 2 | AMBIGUOUS | Reviewer required unstated grounds such as breach/convenience despite a literal document-statement candidate. Legal completeness and textual entailment were conflated. |
| Arbitration in stated venue, page 2 | AMBIGUOUS | The source does not identify a specific venue. This is a legitimate remaining ambiguity for an asserted venue; it must not be repaired or labeled safe. A narrower statement that the document requires arbitration can be evaluated separately, without inventing the venue. |
| Copy of stored records, page 2 | Not generated | The compact response contained six findings; the seventh known clause was omitted. The old six-finding instruction was already removed locally before this follow-up; no subsequent live proof of improved recall exists. |

The complete original rationales, qualifiers and references for all **13 recorded candidates** are preserved in [recorded_accuracy_diagnosis.json](benchmarks/recorded_accuracy_diagnosis.json). It does not mutate the live recordings or relabel a negative verdict.

## Confirmed application gaps fixed in this follow-up

- **Category invisible to the verifier:** `_verification_prompt` previously omitted `category`. It now supplies category without passing the candidate's persuasive rationale, asks for `category_consistent`, and rejects an explicit mismatch as `PROVIDER_CATEGORY_MISMATCH`. Legacy verdicts lacking that field remain readable and are marked category-unassessed; they are not reprocessed or silently promoted. QA has no finding category and is not subjected to this irrelevant gate.
- **Ungrounded reviewer references accepted:** unresolved parser IDs/map aliases absent from the actual text are now rejected as `PROVIDER_VERDICT_UNGROUNDED`. Mentioning a legitimate source locator in a rationale is not incorrectly treated as a legal cross-reference. A valid textual unresolved reference or genuine negative/ambiguous verdict is preserved.
- **Task routing:** optional validated `AI_TASK_PROVIDER_ORDER` reorders only the existing authorized configurations. Candidate generation, indexing, semantic review, translation and QA may have different preferences. Long-source indexing can use a separately preferred authorized indexer while another authorized provider handles semantic review; provenance records both. Default ordering is unchanged, and there is no paid-model selection, new key, permission grant or budget expansion.
- **Auditability:** finding metadata records source-match status, categorical decision basis and category-review state. Model-call metadata distinguishes schema validity from semantic integrity rejection. No confidence score was fabricated.
- **User guidance:** English/Hindi/Hinglish messages distinguish an invented reviewer reference from a rejected finding category. Existing summary, risk, offline, pagination, authorization and cache behavior is preserved.

Source locations: `backend/app/services/analysis.py` (`Verdict`, `_verification_prompt`, `_review_context`, `analyze`), `backend/app/services/context_index.py` (`review`), `backend/app/providers/base.py` (`ordered_configs`, `generate_with_fallback`), `backend/app/config.py`, `frontend/src/lib/providerFailure.ts` and `messages.json`.

## Optional configuration, not applied

An operator can use the existing configured providers for different tasks, for example:

```dotenv
AI_TASK_PROVIDER_ORDER={"candidate_generation":["gemini","groq"],"context_indexing":["gemini","groq"],"semantic_verification":["groq","gemini"],"question_answering":["groq","gemini"]}
```

This is an example, not a measured model-quality recommendation or a billing authorization. A provider absent from user permissions never receives content. Gemini/Groq account-specific zero-cost eligibility and current live inference quality still need separate approval/verification. Existing OpenRouter model compatibility and zero-price gates remain. No `.env` or deployment configuration was changed; no new migration is required.

## What the tests establish

`tests/test_accuracy_review.py` includes recorded fabricated-reference rejection, category visibility/mismatch, preservation of genuine SUPPORTED/UNSUPPORTED/PARTIALLY_SUPPORTED/AMBIGUOUS decisions, authorized alternate review, task-order validation, separate indexing/semantic providers and exact two-page source matching.

The controlled positive fixture has seven programmed valid semantic decisions, yielding **7/7 supported** with original quote/page mappings. Its negative variant yields **3 supported, 2 unsupported, 2 unverified**, with summary Not Determinable. These are explicitly mocked semantic decisions, not newly accurate live model outputs. The real historical counts remain **0/7** and **0/6**.

The synthetic reference is authored, not expert-adjudicated legal ground truth. Some ambiguities, such as the missing stated venue, remain valid. Achieving a useful live result means obtaining actual supported findings and disclosing unresolved material, not forcing the overall summary away from Not Determinable.

## Remaining live gates

No current provider has passed the complete real acceptance case. The new schema/prompt/routing changes require a newly approved, budgeted synthetic inference run before any live reliability claim. A better task-specific authorized reviewer may help, but metadata compatibility and mock success do not prove that. Do not promote old ambiguous findings, weaken quotation checks, rerun private production data, or deploy based on this local test result alone.

## Executed verification

- Backend full suite: **329 passed, 1 skipped**, 136.68 seconds (`python -m pytest tests -q --tb=short`, isolated test environment with live keys disabled).
- Frontend unit tests: **58 passed**. ESLint, TypeScript and production Vite build passed.
- Browser suite: **32 passed, 1 skipped**, including offline/API-blocked mode and recorded live partial-result replay; real production/live-provider browser case intentionally skipped.
- Ruff, targeted Python formatting and `git diff --check` passed.
- PostgreSQL: read-only connection PASS; migration head `c819ba204ae1` matches local files; evidence table has three foreign keys. No database writes or migrations executed. Evidence: [accuracy_postgres_readonly.json](benchmarks/accuracy_postgres_readonly.json).
- Fresh paid or free inference requests: **0**. Historical live counts remain unchanged. No model-quality, cost, latency or production-accuracy improvement is claimed from mocks.
