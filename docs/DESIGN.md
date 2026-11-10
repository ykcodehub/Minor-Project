VERIORA 2.0 — UI/UX & Product Design Specification
Document ID: VER-DES-001Version: 1.0 — Proposed baselineDate: 08 November 2026Owner: Design / Frontend Lead (to assign)Status: Design handoff, pending visual approvalNorth star: Professional, calm, source-focused, accessible. No emoji UI, ornamental badges or manufactured trust claims.
1. Experience strategy
Veriora should feel like a precise document-workspace product rather than a generic chatbot or brightly colored AI showcase. The critical interaction is claim ↔ evidence. Users must be able to answer: What exactly did the document say? Where? What qualification did the AI apply? How reliable is the citation? Every surface must preserve that context.
Visual traits: Minimal, credible, modern, high-contrast, spacious but information-dense where needed; semantic status indicators with clear text; restrained motion; real data instead of demo-like metrics. Existing Veriora frontend can inform brand copy and general visual direction, but functional pages and component hierarchy should be recreated based on this specification.
2. Design tokens (baseline proposal)
Token
Light value
Purpose
--surface
#FFFFFF
Main cards and document workspace
--canvas
#F7F9FA
App background
--text
#17212B
Primary readable text
--muted
#536271
Supporting text
--border
#DDE4E8
Subtle structure
--primary
#176B66
Brand actions, links, active navigation
--primary-hover
#115650
Hover/pressed
--primary-soft
#E9F4F1
Selected states and gentle emphasis
--warning
#946200
Needs review / incomplete (test contrast)
--danger
#B42318
Unsupported/failed, not decorative
--success
#207348
Verified indicator alongside text
--focus
#216BD6
Focus ring independent of brand
Typography: Inter or a reliable system sans-serif for interface, with font fallbacks; source preview preserves document font when practical. Main body 15–16px, line-height 1.5–1.6, table/metadata 12–14px, page headings 28–34px desktop and 24–28px mobile. Prefer tabular numerals for timestamps, page numbers, counts and versions. Base spacing scale 4/8/12/16/24/32/48px; radii 8–12px; one restrained elevation level. Avoid huge shadowed cards, bright gradients, glassmorphism and blur effects that reduce clarity.
Icons: Lucide outline icons only where needed; 16/18/20/24px with consistent stroke. Pair semantic icons with text; never use emoji. No decorative icons in every row. Approved examples: file-text, shield-check, search, upload, link, check-circle-2, alert-triangle, info, external-link, download, copy, trash-2, chevron-right, panel-left-close. No trust shield unless it links to a specific validated control or method.
Dark theme is P1 unless design and contrast testing show it is genuinely ready; no half-implemented dark palette in P0. Support browser zoom up to 200% and reduced-motion preferences.
3. Information architecture
Marketing  /                    Landing (what Veriora does / does not do)Application  /analyze             Source intake: Upload / Paste / Website URL  /discover            Discover candidate legal documents from URL  /analysis/:id        Processing state -> Verified Results Workspace  /library             Saved documents, analyses, exports  /settings            Account, privacy, retention, provider noticesAuthentication  /sign-in             Account login / create / recoveryP1  /compare             Policy versions and related-doc comparisons  /review              Assigned professional reviews
No separate “AI chat homepage” in P0. Q&A belongs to a selected analysis to preserve source scope. Do not add template dashboards with meaningless charts or a huge admin panel until a real operator requirement exists.
4. Global navigation and layout
Desktop (>= 1024px): 64–72px top bar: Veriora wordmark left, Analyze / Library main nav, account menu right. In analysis view, use a compact workspace header with document name/version and source completeness chip. Side navigation or tabs should occupy only necessary width; document preview and finding list receive most of the viewport. No sticky elements obscuring citations.
Tablet (768–1023px): Results switch between tabs for Insights / Source / Q&A, preserving selected finding. Inspector appears as drawer when needed.
Mobile (< 768px): One-column, bottom or top tab strip for Results / Source / Ask. Source highlight scrolls into view after opening the source tab. Filters use dismissible drawer, not a permanently squeezed sidebar. Minimum touch target 44px preferred; preserve label visibility.
Accessibility: Semantic landmarks, proper headings, keyboard navigation, skip link, visible focus, accessible dialogs, live regions for job state, sufficient contrast, no color-only status, no placeholder-only form labels, no autoplay animated counters. Meet WCAG 2.2 AA target with manual QA in addition to tooling.
5. Page-by-page specifications
5.1 Landing /
Goal: Convey what product does without implying court certification or 100% accuracy.
Above fold: small navigation; decisive headline “Understand every clause. Verify every claim.”; two-line explanation; primary CTA “Analyze a document”; secondary “How verification works.” Supporting compact illustration may show one finding linked to a highlighted clause, clearly labeled as example. Keep a factual “Document says vs real-world compliance” trust clarification within the initial scroll.
Below fold: three entry methods (Upload, Paste, Website URL), “How evidence works” 3-step explanation, supported document list, privacy/provider disclosure, transparent limitations, FAQ and legal disclaimer. Avoid aggressive carousels, testimonials that do not exist, fake usage counters, fabricated awards or false “government approved” badges.
Interactions: CTAs route to actual functioning intake page; FAQ accessible accordion; demo finding triggers example source highlight in a locally defined example, not simulated production verification.
5.2 Analyze /analyze
Goal: One obvious action for every input type.
Header: “What would you like to analyze?”; segmented controls: Upload file | Paste text | Website URL. No separate unrelated screen for each initial input. The entry panel has input validation, supported formats, size limits, privacy notice, provider processing notice and a clearly labeled submit button. Show file name/size/type and replace/remove controls. For paste: a text area with character count and source-name field. For URL: normalized URL preview and “Find legal documents” action.
States: idle, drag-over, selected, invalid, too large, unsupported, password-protected, uploading, failed. Error messages identify the reason and a next step; do not display technical stack traces. Disable duplicate submissions and support resume after refresh through job ID.
5.3 Discover /discover
Goal: Prevent silent assumptions that a website’s entire legal corpus was found.
Top: submitted domain, fetch date, “Discovery coverage” summary. Content: list of candidate cards with legal-document type, full source URL, official-link path, HTTP availability and last-seen timestamp. Checkboxes/select controls allow choosing which pages to analyze. A separate “Not found / inaccessible” group lists categories investigated but unavailable. Clear action “Analyze 3 selected documents.”
Important microcopy: “Veriora found these accessible documents linked from the website. Other terms may exist.” Never show a green “all policies found” claim unless a defined completeness test is genuinely satisfied.
5.4 Processing and status /analysis/:id
The processing page is the same route as the final result; user does not need to navigate when processing finishes. Show progress steps with named status: Received, Validating, Extracting, Structuring, Analyzing, Verifying, Preparing results. Stages display Actual State (queued/current/done/failed) and optional measured count (e.g. “8 of 12 chunks processed”), not artificial percentages. Provide cancel when supported, non-destructive “Back to library,” and retry for failed stages. Refresh restores server state.
For partial completion, show processed source coverage plus “Some sections were not analyzed” warning. Accessible status updates should not announce every poll to screen readers; announce meaningful stage changes.
5.5 Results Workspace /analysis/:id
Primary desktop composition:
+--------------------------------------------------------------------------------+| Veriora | Document name / source version             Export  More / Settings   |+--------------------------------------------------------------------------------+| Overview  Findings  Rights & Duties  Ask Veriora  Coverage                    |+--------------------------------------+-----------------------------------------+| FINDINGS LIST                        | ORIGINAL SOURCE VIEWER                  || Search [____________]  Filters       | File title     Page 23 / 42   Zoom      ||                                      |                                         || [SUPPORTED] Third-party sharing      | ...original paragraphs...              || Requires consent; exception...       | [highlighted clause 8 text]           || Clause 8 - page 23                   | ...surrounding context...              ||                                      |                                         || [PARTIAL] Data deletion              | Evidence Passport                      || Missing retention details...         | Quote validity, support rationale      ||                                      | Capture date, source hash, limitations |+--------------------------------------+-----------------------------------------+
Hierarchy: One concise outcome summary and source completeness banner; below, filterable findings with category and evidence-state tabs. At desktop width, clicking finding synchronizes viewer and opens evidence detail; at small widths it opens source tab. Selected state uses subtle background plus left accent, never color alone.
Finding card anatomy: short declarative claim, status text + icon, category, exact source locator, brief rationale, exception marker if present, keyboard-operable “View evidence.” Details panel contains exact quote, surrounding context, verifier explanation, model metadata collapsed by default, and controls Copy reference / Add to report.
Coverage view: processed/total pages, unprocessed sections, OCR status, missing linked docs and provider failures. Absence of finding never means permission or prohibition. Show coverage before interpreting “no relevant clause found.”
Risk UI: Use “Potentially restrictive” or “Needs review” and a reasoned impact statement; no uncalibrated red risk percentage, no definitive “illegal clause” label. High-impact findings can surface in an attention panel if verified and contextually explained.
5.6 Ask Veriora (analysis-scoped)
Ask is a docked workspace tab, not an independent infinite chat. Every answer card contains direct answer, cited source chips, exceptions and uncertainty. Citation chip navigates to highlighted source; no answer without citations unless it is an explicit abstention. A persistent scope label (“Answering from: 2 selected policies captured on [date]”) prevents confusion with general web chat. Optional suggested questions are based on detected categories, not fictitious analysis results.
Example: User asks “Can they share data without my consent?” Safe answer format: “This policy says consent is generally required, but Clause 8 includes a legal-disclosure exception [Source]. This does not establish what the company does in practice.”
5.7 Library /library
Minimal sortable table/list, search and filters: document name, source type, captured date, processing state, last analyzed, exports. Actions: Open, Rename (display title only), Download report, Delete. Empty state directs to Analyze. P0 no arbitrary charts, habit streaks or analytics widgets. Confirmation dialog describes deletion scope and exceptions; progress shows pending deletion if asynchronous.
5.8 Settings and authentication
Settings groups: Account, Document retention, AI provider/data handling, Delete account, Export data; descriptions explain actual implementation. Login has clear validation, focus return, password recovery and email verification; never show security theater badges. The confidential-document mode is visible during intake and can block external model submission until a permitted processing route exists.
5.9 Compare and reviewer screens (P1)
Source version compare: select two captures, show original text on both sides with additions/removals, aligned clause IDs, ambiguous alignments visibly marked. Reviewer: assigned queue, claim/quote/context, approve/reject/request changes, reason and audit trail. Review approval must be distinct from AI-source validation; both statuses displayed.
6. Component inventory — create only what is used
Component
Function
Reuse
AppShell
Navigation, max-width, content landmarks
All app pages
Button, IconButton
Accessible actions with loading state
Global
Input, Textarea, FieldError
Labeled form elements
Forms
Tabs, Dialog, Drawer
Accessible complex interactions
Where needed
FileDropzone
File input, keyboard/drag, validation
Analyze
PolicyCandidateRow
Discovery URL evidence + select
Discover
JobProgress
Real stage status and counts
Analyze/Results
FindingCard
Atomic claim with category/status/location
Results
DocumentViewer
PDF/HTML/text preview + highlight
Results/Compare
EvidencePassport
Quote, provenance, verifier context
Results/export
CoverageNotice
Missing source segments and warnings
Results
QuestionAnswer
Evidence-first Q&A answer with links
Ask
EmptyState, ErrorState, Skeleton
Accurate async UX
Reuse
Use accessible Radix primitives only for complex interactions that justify them; build simple controlled components natively. Do not install a whole component library solely to use two buttons.
7. Interaction contracts
Trigger
Response
Accessibility/edge behavior
File drag enters
Outline change + text instruction
Keyboard file picker always available
Upload begins
Actual upload status and cancellation only if supported
Progress live region, no fake percentages
Analysis stage changes
Update server-confirmed stage + measured units
Avoid repetitive screen-reader announcements
Finding selected
Scroll document viewer to original span and highlight
Focus/selection context preserved
Source unavailable
Show “Unavailable” with URL and reason
Never render empty panel as “no issue”
Citation invalid
Show rejected citation and explanation
No verified state or success color
Ask returns no evidence
Abstention with source-coverage context
Clear alternative action
Export requested
Progress + audit status
Prevent duplicate download jobs
Delete requested
Confirmation + exact scope
Restore focus; block accidental loss
Provider failure
Controlled error with retry if safe
No model implementation details leaked
Motion: 120–180ms transitions for hover/dialogs if not reduced-motion; no perpetual spinners without status. Skeletons represent layout, not fake content. Use aria-busy and a polite live region for major stage changes.
8. Content design / terminology
Avoid
Preferred product copy
“100% correct analysis”
“Checkable findings linked to source text”
“Court-approved evidence”
“Export source and verification metadata”
“Company never shares data”
“The policy states that sharing requires consent, with stated exceptions”
“All legal policies found”
“3 accessible policy pages discovered; others may exist”
“No risk”
“No supported risk note identified in the processed content”
“AI confidence: 99.9%”
“Supported by source” / “Needs review”
“We scanned everything”
“Processed 38 of 42 pages; 4 pages require review”
“This clause is illegal”
“Potential legal concern; professional review may be appropriate”
Statuses must not rely solely on a tooltip. Always surface document acquisition date and relevant limits near user decisions.
9. Responsive, accessibility, visual QA and performance
Responsive breakpoints proposed: mobile <768px, tablet 768–1023px, desktop >=1024px. Layout should remain usable at 320 CSS px and 200% zoom; verify actual breakpoints rather than designing only at one width.
Text contrast target >=4.5:1 normal and >=3:1 large; graphical controls and focus need measurable accessibility checks. Colors above are starting tokens and must be tested on final component combinations.
Full keyboard path: start analysis, choose input, upload/select file, submit, review progress, filter results, navigate citations, view source, export, delete. Maintain visible focus and escape/close semantics.
Document viewer supports zoom, keyboard page navigation, copy passage and direct citation links. When exact PDF geometry unavailable, show text excerpt with a clear approximate-location label instead of fake highlight.
Optimize by route-based code splitting; dynamically import PDF viewer rather than loading it on landing page. Virtualize long lists only if profiling proves necessary. Server-side pagination for document libraries and long findings lists.
Accessibility audit with screen readers, keyboard only, color deficiency simulation and reduced-motion setting. E2E tests cover mobile viewport, tablet, desktop and low-bandwidth/error conditions.
10. Handoff and sign-off checklists
Designer handoff: page purpose, interaction states, source locator annotation, component usage, responsive behavior, content copy, keyboard flow and acceptance test are recorded before build. A future Figma design can follow these specifications but is not a prerequisite to backend engineering.
Frontend handoff: API response shape is versioned, all route states modeled, empty/error/partial states implemented, no placeholder dashboard numbers, no emoji, correct loading semantics, design tokens centralized in one stylesheet/config, icon names consistently applied.
Review criteria: (1) Can a new user start analysis without a tutorial? (2) Can every verified claim be traced to the exact source? (3) Can the user see what was not analyzed? (4) Are limitations visible at the point of decision? (5) Does the screen work without a mouse? (6) Is the interface professional without suggesting unsupported authority?
11. Team allocation and no-waste design governance
Work package
Suggested owner
Dependencies
Acceptance demo
DS-01 Brand tokens / primitives
UI lead
Product copy
Token sheet + keyboard-ready primitives
DS-02 Analyze / Discovery
Frontend A
FR-ING/URL, API mocks
Upload and URL error/success journeys
DS-03 Analysis workspace / viewer
Frontend B
Source locators, FR-AI schema
Finding click -> exact highlighted evidence
DS-04 Q&A / Export / Library
Frontend B or shared
Auth and job APIs
Scoped answer and authorized export
DS-05 Accessibility and responsive QA
QA / UI lead
All pages
Recorded audits and fixes
Keep design source, tokens and implementation aligned. No separate components/common/ui/components nesting, duplicated navigation bars, placeholder pages, or variants without a real product state. Changes to trust labeling or evidence status require Product + QA review, not only visual approval.
12. Minimum design approval artifacts
Four clean documents are the current pre-development deliverable. After approval, implementation should start with a single clickable UI prototype or Figma file containing Landing, Intake, Discovery, Processing, Results/Evidence, Ask, Library, Settings states—not an enormous speculative design system. Design approval is contingent on real content examples with exceptions, unsupported findings, partial coverage and mobile evidence navigation.
## 10 November 2026 interaction amendment

Keep the existing workspace and its default Detailed Analysis view. Add a compact Summary/Detailed Analysis tab pair and English/Hindi (हिन्दी)/Hinglish selector above it. Summary uses restrained cards for benefits, obligations, restrictions, potential risks and exceptions. Show assessment category, expandable documented rule and source/real-world conduct distinction. Empty categories do not imply a provision is absent. Original quotes retain source language; page/section actions restore detailed evidence navigation. A clear Prepare verified translation action explains provider usage and keeps English visible until a translation passes checks. No fabricated confidence/risk percentages.

Account settings persist explanation language and expose explicit Google linking. Auth supports /sign-in, /register, /verify-email, /forgot-password and /reset-password through shared form components. Google button reflects configuration availability. Email signup never implies activation before verification; verification asks for the chosen password. Recovery uses neutral anti-enumeration copy. Verification links use fragments and are cleared from the address bar. Loading/error/success feedback remains visible and keyboard-operable. No emojis or decorative trust seals.

Automated mobile, source navigation, multilingual headings and original quote preservation checks accompany the existing axe/public-screen and token-lifecycle tests. Full manual screen-reader/linguistic review remains pending.

## Current design amendment — header language and Summary

The global header includes a compact Lucide globe action with a labeled English/Hindi/Hinglish select, keyboard access and Escape dismissal. The chosen language applies immediately across navigation and feature pages. Remove the duplicate analysis/settings language selectors. Retain original source quotes and stable citation coordinates, and clearly disclose when document explanation translation is unavailable.

Summary uses a restrained white/neutral layout: overview and risk panel, textual Low/Moderate/High/Not Determinable indicator with Lucide status icon, visible high/unknown warnings, category cards, exact source blockquotes and clickable locators. A separate method rail explains limitations and assessment rules. Counts represent unique displayed supported findings; no decorative risk gauge or confidence percentage. Collapse to one column on small screens. Keep the Summary/Detailed Analysis switch and evidence viewer intact.

Registration displays Email -> Verify -> Password steps. Initial signup has only email; after clicking the emailed verification link, show Create Password and Confirm Password. Login remains email/password plus Google and recovery. Pending/success/error states are explicit and account-existence-neutral. No fake OTPs, emojis or activation shortcuts.


## 2026-11-10: final UI and deployment preparation

Summary is the default analysis presentation. Summary/Detailed Analysis tabs remain directly below the heading. Compact risk/category cards show key information; quotes, qualifications and rationale expand through Source & context. Large categories expose two clauses initially and Show more. Detailed Analysis retains source, finding filters, passports, chat and exports; Processing Coverage appears in a collapsed bottom disclosure. Processing diagnostics expand separately from the current real stage. Veriora AI opens with concise scope and supported-category question suggestions. Global English/Hindi/Hinglish and original source quotations are preserved. Header uses a 32px logo frame loading /logo.png with text fallback; footer flows below content without overlaying the workspace.


## Cleanup and hardcoding review (10 November 2026)

Remove decorative dots from both header/footer wordmarks, retaining domain names and ordinary sentence punctuation. Main navigation uses restrained background/underline transitions, explicit active states and keyboard outlines; reduced-motion disables transitions. Summary reading guidance is initially collapsed while source-linked findings remain accessible. Veriora AI uses a short neutral localized prompt rather than assuming a cancellation or data-sharing provision. Exact quotations remain unchanged.

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

## 11 November 2026 amendment: bounded indexed verification

Use a shared source-wide qualification index with exact validated quotations and bounded semantic review, not a per-finding 12-window cutoff. Display source-audit coverage separately from finding support and workflow completion. Preserve original source identifiers/pages/offsets through reversible wire aliases. Reuse durable completed request checkpoints on explicit retry; require cost acknowledgment for interrupted uncertain requests. Global call/token reservations survive retry. Neither retrieval nor a completed model-assisted index certifies correctness. The 10–15-page target is validated using synthetic PDFs and mocked inference only; production model quality, quotas and combined hosting memory remain unverified. See README and docs/benchmarks/BENCHMARKS.md for implementation limits and execution evidence.
