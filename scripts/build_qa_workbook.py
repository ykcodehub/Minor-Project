"""Build the QA workbook from recorded results; never execute production mutations."""

import ast
import json
import re
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import xlsxwriter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/testing"
E = OUT / "evidence"
NOW = datetime.now(UTC).isoformat(timespec="seconds")
DATE = NOW[:10]
ROWS = []
COMMANDS = []
STATUSES = ["PASS", "FAIL", "BLOCKED", "NOT RUN", "NOT IMPLEMENTED"]
HEADERS = [
    "Test Case ID",
    "Module / Feature",
    "Test Scenario",
    "Preconditions",
    "Test Steps",
    "Test Input / Test Data",
    "Expected Result",
    "Actual Result",
    "Status",
    "Severity / Priority",
    "Error Details",
    "Recommended Fix",
    "Execution Date (UTC)",
    "Evidence / Source",
    "Environment",
    "Test Type",
    "Duration (ms)",
    "Requirement Trace",
]


def read_log(path):
    data = path.read_bytes()
    return (
        data.decode("utf-16")
        if data.startswith((b"\xff\xfe", b"\xfe\xff"))
        else data.decode("utf-8-sig", errors="replace")
    )


def load(name):
    return json.loads((E / name).read_text(encoding="utf-8-sig"))


def add(
    ident,
    module,
    scenario,
    pre,
    steps,
    data,
    expected,
    actual,
    status,
    severity="High / P1",
    error="None observed",
    fix="None for this case; retain regression coverage",
    evidence="",
    environment="Local isolated",
    kind="Regression",
    duration=None,
    requirement="",
):
    assert status in STATUSES
    ROWS.append(
        [
            ident,
            module,
            scenario,
            pre,
            steps,
            data,
            expected,
            actual,
            status,
            severity,
            error,
            fix,
            DATE,
            evidence,
            environment,
            kind,
            duration,
            requirement,
        ]
    )


def module_for(text):
    value = text.lower()
    if any(
        k in value for k in ("oauth", "google", "identity", "signup", "registration", "password", "auth_")
    ):
        return "Authentication & sessions"
    if any(k in value for k in ("summary", "language", "translation", "localization", "risk")):
        return "Risk & multilingual"
    if "comparison" in value or "compare" in value:
        return "Document comparison"
    if "mcp" in value:
        return "MCP authorization"
    if any(k in value for k in ("s3", "r2", "storage", "render", "production", "vercel")):
        return "Storage & deployment"
    if any(
        k in value
        for k in ("processing", "ingest", "chunk", "pdf", "extraction", "docx", "discovery", "unsafe_url")
    ):
        return "Ingestion & discovery"
    if any(k in value for k in ("test_ai", "semantic", "citation", "evidence", "provider", "question")):
        return "AI & evidence"
    if any(
        k in value for k in ("lifecycle", "migration", "postgres", "retention", "deletion", "lease", "job")
    ):
        return "Database & worker"
    if any(k in value for k in ("report", "export")):
        return "Reports & history"
    if any(k in value for k in ("api", "completion")):
        return "API integration"
    return "Frontend & navigation"


def security(text):
    return bool(
        re.search(
            r"auth|oauth|csrf|password|session|token|cookie|replay|nonce|expired|isolat|ownership|unsafe|ssrf|forg|redact|confidential|consent|security|encrypt|scope|permission|private|invalid|rate.limit",
            text,
            re.IGNORECASE,
        )
    )


def source_info(file, function):
    path = ROOT / file
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function
        ),
        None,
    )
    if node is None:
        return (
            "See linked test source assertions",
            "See synthetic fixture in linked source",
            "See linked test body",
            file,
        )
    assertions = [ast.get_source_segment(source, n) for n in ast.walk(node) if isinstance(n, ast.Assert)]
    expects = [
        ast.get_source_segment(source, n)
        for n in ast.walk(node)
        if isinstance(n, ast.With) and "pytest.raises" in (ast.get_source_segment(source, n) or "")
    ]
    strings = []
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and n.value
            and len(n.value) < 180
            and n.value not in strings
        ):
            strings.append(n.value)
    fixtures = [a.arg for a in node.args.args]
    expected = (
        "\n".join(assertions[:10])
        or "\n".join(expects[:2])[:2400]
        or "All explicit checks in linked source complete without error"
    )
    calls = []
    for n in node.body:
        segment = ast.get_source_segment(source, n) or ""
        if not isinstance(n, ast.Assert) and segment:
            calls.append(segment[:450])
    steps = (
        "1. Run the exact test node using pytest from backend.\n2. Fixture/parameters: "
        + ", ".join(fixtures)
        + ".\n3. Test operations: "
        + "\n".join(calls[:5])
        + "\n4. Evaluate the listed source assertions."
    )
    return (
        expected[:5000],
        "Synthetic literals: " + " | ".join(strings[:10])[:1600] + "; parameter variant is in test node ID.",
        steps[:4500],
        f"{file}:{node.lineno}",
    )


def backend_cases():
    tree = ET.parse(E / "backend-junit.xml")
    for i, t in enumerate(tree.findall(".//testcase"), 1):
        classname = t.attrib.get("classname", "")
        file = "backend/" + classname.replace(".", "/") + ".py"
        name = t.attrib["name"]
        function = name.split("[", 1)[0]
        expected, data, steps, ref = source_info(file, function)
        skipped = t.find("skipped")
        failure = t.find("failure")
        error = t.find("error")
        status = (
            "BLOCKED"
            if skipped is not None
            else "FAIL"
            if failure is not None or error is not None
            else "PASS"
        )
        detail = (
            skipped.attrib.get("message", "")
            if skipped is not None
            else (failure if failure is not None else error).attrib.get("message", "")
            if failure is not None or error is not None
            else "None observed"
        )
        node = classname.replace(".", "/") + ".py::" + name
        actual = (
            ("Not executed: " + detail)
            if status == "BLOCKED"
            else (
                "pytest completed all assertions; isolated fixtures/mocked external boundaries; not a live production certification"
                if status == "PASS"
                else "pytest reported assertion/setup failure: " + detail
            )
        )
        kind = (
            "Security / negative / regression" if security(file + name) else "Unit / integration / regression"
        )
        add(
            f"BE-{i:03}",
            module_for(file + name),
            name.replace("test_", "", 1).replace("_", " "),
            "Project virtual environment; synthetic fixtures; production-write opt-in disabled; no live provider calls",
            steps,
            data,
            expected,
            actual,
            status,
            error=detail,
            fix="Authorize a dedicated disposable PostgreSQL integration database before execution"
            if status == "BLOCKED"
            else "Investigate failing assertion in linked node"
            if status == "FAIL"
            else "Retain regression coverage",
            evidence=f"evidence/backend-junit.xml | {ref} | pytest node: {node}",
            kind=kind,
            duration=float(t.attrib.get("time", 0)) * 1000,
        )


def frontend_cases():
    i = 0
    for suite in load("frontend-unit.json")["testResults"]:
        relative = Path(suite["name"]).relative_to(ROOT).as_posix()
        for t in suite["assertionResults"]:
            i += 1
            name = t.get("fullName") or " > ".join(t.get("ancestorTitles", []) + [t["title"]])
            status = {
                "passed": "PASS",
                "failed": "FAIL",
                "pending": "NOT RUN",
                "todo": "NOT RUN",
                "skipped": "NOT RUN",
            }.get(t["status"], "NOT RUN")
            message = "; ".join(t.get("failureMessages", []))[:2500]
            add(
                f"FE-{i:03}",
                module_for(relative + name),
                name,
                "Vitest/jsdom with test setup; synthetic state and mocked HTTP; no production requests",
                "Run npm test; execute named assertion in "
                + relative
                + "; inspect rendered state and events asserted in source.",
                "Synthetic component props, citations, profiles and languages from " + relative,
                "All explicit expect() checks in the named test pass; exact quotations and accessible behavior preserved where asserted.",
                "Vitest " + t["status"] + "; " + (message or "named assertions completed"),
                status,
                error=message or "None observed",
                evidence="evidence/frontend-unit.json | " + relative,
                environment="Local isolated",
                kind="Frontend / unit / regression" + (" / security" if security(name + relative) else ""),
                duration=t.get("duration"),
            )


def browser_cases():
    source = ROOT / "frontend/test-results/results.json"
    shutil.copyfile(source, E / "browser-e2e.json")
    i = 0

    def walk(suites):
        nonlocal i
        for suite in suites:
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    i += 1
                    result = test.get("results", [{}])[-1]
                    state = result.get("status", "skipped")
                    status = {
                        "passed": "PASS",
                        "failed": "FAIL",
                        "timedOut": "FAIL",
                        "interrupted": "FAIL",
                        "skipped": "BLOCKED",
                    }.get(state, "NOT RUN")
                    errors = "; ".join(str(e.get("message", e))[:1500] for e in result.get("errors", []))
                    why = (
                        "Live AI/account production workflow is not authorized; explicit verified synthetic account and live opt-in required"
                        if status == "BLOCKED"
                        else errors or "None observed"
                    )
                    ref = (
                        "frontend/e2e/"
                        + Path(spec.get("file", suite.get("file", ""))).name
                        + ":"
                        + str(spec.get("line", 0))
                    )
                    add(
                        f"E2E-{i:03}",
                        module_for(spec["title"]),
                        spec["title"],
                        "Isolated local FastAPI/worker/Vite servers; temporary SQLite and encrypted storage; synthetic Google/mail/provider boundaries",
                        "Run npm run test:e2e; harness starts isolated services; execute Playwright scenario; assert navigation, visible evidence and API-driven outcomes.",
                        "Authored synthetic document/account fixtures in " + ref,
                        "Every explicit Playwright assertion succeeds; no real Google consent or paid AI call implied.",
                        "Playwright " + state + "; " + why,
                        status,
                        error=why,
                        fix="Provide separately authorized verified synthetic account/live AI budget"
                        if status == "BLOCKED"
                        else "Investigate linked trace/assertion"
                        if status == "FAIL"
                        else "Retain regression coverage",
                        evidence="evidence/browser-e2e.json | evidence/browser-e2e.log | " + ref,
                        kind="Browser / E2E / regression"
                        + (" / security" if security(spec["title"]) else ""),
                        duration=result.get("duration"),
                    )
            walk(suite.get("suites", []))

    walk(load("browser-e2e.json").get("suites", []))


def production_cases():
    for rec in load("production-http.json"):
        expected = f"GET returns HTTP {rec['expected']} and the expected JSON contract where applicable."
        if rec.get("origin"):
            expected += (
                " Untrusted origin must not be reflected."
                if "untrusted" in rec["origin"]
                else " Access-Control-Allow-Origin must equal the frontend origin."
            )
        fix = "Inspect service/network availability; no automatic production change"
        if rec["id"] == "PROD-HTTP-04":
            fix = "Choose routing contract: use /api/v1 with an external API rewrite, OR full Render URL ending /api/v1 with correct CORS. Same-origin proxy is optional if direct API is deliberate."
        if rec["id"] in {"PROD-HTTP-13", "PROD-HTTP-14"}:
            fix = "Configure Vercel SPA fallback to /index.html after the API rewrite; redeploy only after approval."
        if rec["id"] == "PROD-HTTP-12":
            fix = "Allow exactly https://veriora.vercel.app in Render ALLOWED_ORIGINS for credentialed direct API calls; review overrides and redeploy manually."
        add(
            rec["id"],
            "API integration",
            rec["scenario"],
            "Public production HTTPS; anonymous client; no cookies or account; GET only",
            "1. Send one anonymous GET to "
            + rec["url"]
            + ". 2. Inspect status/whitelisted headers and safe JSON fields. 3. Compare with expected contract.",
            rec["input"] + ("; Origin=" + rec["origin"] if rec.get("origin") else ""),
            expected,
            rec["actual"],
            rec["status"],
            error=rec["actual"] if rec["status"] != "PASS" else "None observed",
            fix=fix if rec["status"] != "PASS" else "Retain production smoke monitoring",
            evidence="evidence/production-http.json # " + rec["id"],
            environment="Production read-only",
            kind="API / integration / security"
            if security(rec["scenario"]) or rec.get("origin")
            else "API / integration",
            duration=rec.get("duration_ms"),
        )
    data = load("production-browser.json")
    for rec in data["records"]:
        ident = rec["id"]
        fix = "Inspect observed public UI failure without submitting forms or changing deployment"
        if ident in {"PROD-UI-04", "PROD-UI-05", "PROD-UI-06", "PROD-UI-07", "PROD-UI-08", "PROD-UI-09"}:
            fix = "Add/review Vercel SPA fallback to index.html; direct navigation must serve the app."
        if ident in {"PROD-UI-10", "PROD-UI-11"}:
            fix = "Correct credentialed CORS and frontend API base; verify public GETs before authorizing account workflows."
        if ident in {"PROD-UI-13", "PROD-UI-16"}:
            fix = "Set frontend VITE_API_BASE_URL to https://veriora-api.onrender.com/api/v1 OR /api/v1 with a working rewrite. Rebuild frontend and correct CORS. Never place API credentials in VITE_* values."
        expected = "Named visible UI/navigation/accessibility condition succeeds in real Chromium; no submission or OAuth initiation."
        if ident == "PROD-UI-16":
            expected = (
                "Browser requests /api/v1/me and /api/v1/auth/options, matching deployed backend routes."
            )
        if ident == "PROD-UI-10":
            expected = "Credentialed browser GET to backend health completes HTTP200 without CORS rejection."
        add(
            ident,
            "Frontend & navigation",
            rec["scenario"],
            rec["environment"],
            "Navigate public URL or use only non-submitting local UI controls; record HTTP/UI outcome; network guard rejects mutation/OAuth requests.",
            "Production public pages; 1440/375px Chromium; no credentials or uploaded content",
            expected,
            rec["actual"],
            rec["status"],
            error=rec["actual"] if rec["status"] != "PASS" else "None observed",
            fix=fix if rec["status"] != "PASS" else "Retain read-only smoke coverage",
            evidence="evidence/production-browser.json # " + ident + " | embedded production screenshots",
            environment="Production read-only",
            kind="Frontend / E2E / security"
            if ident in {"PROD-UI-03", "PROD-UI-10", "PROD-UI-11", "PROD-UI-13"}
            else "Frontend / E2E",
            duration=rec.get("duration_ms"),
        )


def derived_checks():
    records = {r["id"]: r for r in load("production-http.json")}
    frontend = records["PROD-HTTP-03"]
    backend = records["PROD-HTTP-01"]
    checks = [
        (
            "SEC-HTTP-01",
            "Frontend HTTPS HSTS",
            frontend,
            "strict-transport-security",
            lambda v: "max-age=" in v,
            "Enable an approved HSTS policy on the HTTPS frontend.",
        ),
        (
            "SEC-HTTP-02",
            "Frontend Content-Security-Policy",
            frontend,
            "content-security-policy",
            lambda v: bool(v),
            "Add a reviewed CSP in Vercel headers; test script/style/connect and OAuth behavior before deployment.",
        ),
        (
            "SEC-HTTP-03",
            "Frontend clickjacking protection",
            frontend,
            "x-frame-options",
            lambda v: (
                v.upper() == "DENY"
                or "frame-ancestors" in frontend.get("headers", {}).get("content-security-policy", "")
            ),
            "Set frame-ancestors in CSP or X-Frame-Options. Missing header is a hardening gap, not proof of exploitability.",
        ),
        (
            "SEC-HTTP-04",
            "Backend MIME-sniffing protection",
            backend,
            "x-content-type-options",
            lambda v: v.lower() == "nosniff",
            "Preserve nosniff middleware.",
        ),
        (
            "SEC-HTTP-05",
            "Backend private response caching policy",
            backend,
            "cache-control",
            lambda v: "no-store" in v.lower(),
            "Preserve no-store for API responses.",
        ),
        (
            "SEC-HTTP-06",
            "Backend referrer protection",
            backend,
            "referrer-policy",
            lambda v: v.lower() == "no-referrer",
            "Preserve no-referrer middleware.",
        ),
    ]
    for ident, scenario, rec, key, predicate, fix in checks:
        value = rec.get("headers", {}).get(key, "")
        status = "BLOCKED" if rec.get("http_status") != 200 else "PASS" if predicate(value) else "FAIL"
        add(
            ident,
            "Security hardening",
            scenario,
            "Recorded public production GET response; no account or mutation",
            "Inspect the named security header in captured response; compare with expected defense-in-depth policy.",
            rec["url"],
            scenario + " is present and valid for the sampled response.",
            key + "=" + (value or "ABSENT"),
            status,
            severity="Medium / P2",
            error="Header absent or mismatched" if status == "FAIL" else "None observed",
            fix=fix if status != "PASS" else "Retain header regression checks",
            evidence="evidence/production-http.json # " + rec["id"],
            environment="Production read-only",
            kind="Security / headers",
        )
    for i, ident in enumerate(["PROD-HTTP-01", "PROD-HTTP-02", "PROD-HTTP-03", "PROD-HTTP-09"], 1):
        rec = records[ident]
        add(
            f"PERF-OBS-{i:02}",
            "Performance observations",
            "Capture single-request latency: " + rec["scenario"],
            "One bounded anonymous HTTPS GET; no load generation",
            "Read monotonic client elapsed time around the recorded request; record payload size and HTTP outcome.",
            rec["url"],
            "Record a finite elapsed sample and size; no latency SLA/pass threshold has been approved.",
            f"{rec.get('duration_ms')} ms; {rec.get('bytes', 'unavailable')} bytes; HTTP {rec.get('http_status', 'unavailable')}; observation only, not p95 or load certification",
            "PASS" if rec.get("http_status") is not None else "BLOCKED",
            severity="Low / P3",
            evidence="evidence/production-http.json # " + ident,
            environment="Production read-only",
            kind="Performance / measurement",
            duration=rec.get("duration_ms"),
        )
    local = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    operations = {
        m.upper() + " " + path
        for path, methods in local["paths"].items()
        for m in methods
        if m in {"get", "post", "patch", "delete", "put"}
    }
    remote = records["PROD-HTTP-10"].get("operations")
    if remote is not None:
        missing = sorted(operations - set(remote))
        add(
            "API-SCHEMA-01",
            "API integration",
            "Deployed operation inventory includes local OpenAPI contract",
            "Public local/deployed schema snapshots available",
            "Compare HTTP method + route template sets, without invoking any mutation endpoint.",
            f"Local {len(operations)} operations; deployed {len(remote)} operations",
            "All local operation templates are represented in production schema; this does not prove functional implementation.",
            "Missing: " + ("; ".join(missing) or "none"),
            "FAIL" if missing else "PASS",
            error="Contract/version drift" if missing else "None observed",
            fix="Review deployed commit and intentional API version differences"
            if missing
            else "Retain schema contract checks",
            evidence="docs/openapi.json | evidence/production-http.json # PROD-HTTP-10",
            environment="Production read-only",
            kind="API / contract / integration",
        )
    safe_completed = {"GET /api/v1/health", "GET /api/v1/ready", "GET /api/v1/auth/options"}
    for i, operation in enumerate(sorted(operations - safe_completed), 1):
        method, path = operation.split(" ", 1)
        schema = local["paths"][path][method.lower()]
        scenario = schema.get("summary", operation)
        body = schema.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
        data = (
            "Authorized synthetic account and test-owned identifiers; request contract "
            + json.dumps(body, ensure_ascii=False)[:800]
        )
        pre = "Explicit production authorization and verified synthetic account; approved disposable documents and AI budget if applicable"
        add(
            f"API-PROD-{i:03}",
            module_for(operation),
            "Production success contract: " + operation + " (" + scenario + ")",
            pre,
            "1. Obtain approval/test identity. 2. Provision only approved synthetic fixtures. 3. Invoke exact operation with CSRF/ownership controls. 4. Verify response and authorized persistence. 5. Perform separately approved cleanup.",
            data,
            "Success response matches OpenAPI, ownership, state transitions and evidence semantics; negative authorization is covered separately.",
            "Not invoked against production: account/data mutation, private-document access or external integration authorization is absent.",
            "BLOCKED",
            error="Production workflow prerequisites/authorization not supplied",
            fix="Authorize a dedicated staging environment or bounded production test identity/data/budget first",
            evidence="docs/openapi.json | linked local automated cases in this workbook",
            environment="Production restricted",
            kind="API / positive / integration / E2E",
        )


MANUAL = [
    (
        "Registration",
        "Complete real email-first signup and mailbox receipt",
        "Verified disposable mailbox; explicit permission to create a test account",
        "Enter synthetic email, submit, inspect delivered expiring link, verify, create/confirm password, then sign in",
        "Account is created only after verified ownership; no fake OTP; actual mailbox delivery confirmed",
        "BLOCKED",
        "Account creation and email delivery are not authorized",
        "Authentication & sessions",
    ),
    (
        "Registration",
        "Existing-email anti-enumeration across UI, message and timing",
        "Two approved synthetic addresses with known existence states",
        "Submit registration/recovery for both under approved rate limits; compare content/status and statistically sufficient timing",
        "No public existence disclosure; link delivery semantics remain secure",
        "BLOCKED",
        "Requires accounts, outbound mail and authorization",
        "Authentication & sessions",
    ),
    (
        "Google OAuth",
        "Real Google consent, callback, secure session and dashboard",
        "Approved Google test user and permission for OAuth/state/account changes",
        "Click Google; complete consent; verify canonical callback, state/nonce/PKCE and authenticated dashboard",
        "Valid identity creates an isolated session; wrong/replayed identity is rejected",
        "BLOCKED",
        "Real consent and state/account writes prohibited without authorization",
        "Authentication & sessions",
    ),
    (
        "Password reset",
        "Real SMTP reset link, single use and old-session invalidation",
        "Verified synthetic user and approved mailbox",
        "Request link, set new password, verify old password/session rejection and replay expiry",
        "Real delivery and secure reset work; old sessions invalidated",
        "BLOCKED",
        "Requires outbound mail and account changes",
        "Authentication & sessions",
    ),
    (
        "Sessions",
        "Real production cookie flags, expiration and logout",
        "Approved synthetic login",
        "Inspect Set-Cookie properties without recording values; logout and retry protected routes",
        "HttpOnly/Secure/SameSite/Path correct; expired/revoked session rejected",
        "BLOCKED",
        "No authorized production login",
        "Authentication & sessions",
    ),
    (
        "Document upload",
        "Production PDF/DOCX/TXT/HTML end-to-end persistence",
        "Approved account, authored synthetic documents and R2 mutation approval",
        "Upload each format, observe job status, inspect text/provenance and retrieve owned original",
        "Correct extraction, encrypted R2 objects, owned PostgreSQL metadata, no cross-user access",
        "BLOCKED",
        "Document/account production writes not authorized",
        "Ingestion & discovery",
    ),
    (
        "Upload boundaries",
        "Production zero-byte, mismatch, exactly-max and max-plus-one files",
        "Approved staging account and configured limit known",
        "Submit empty, MIME-mismatched, exact-limit and over-limit synthetic files",
        "Correct validation; bounded parser resources; consistent errors and no leaked content",
        "BLOCKED",
        "Production uploads not authorized; negative fixtures run locally",
        "Ingestion & discovery",
    ),
    (
        "PDF extraction",
        "Visual page accuracy and difficult-layout benchmark",
        "Synthetic multi-column, multi-page, table, Unicode and rotated PDFs; reviewer",
        "Compare extracted passages/page anchors to exact authored source and assess omissions",
        "Citations point to actual pages; omissions are disclosed, never fabricated",
        "NOT RUN",
        "Human visual benchmark not executed",
        "Ingestion & discovery",
    ),
    (
        "Smart chunking",
        "Very long and cross-boundary clause quality benchmark",
        "Authored long documents and approved local resource budget",
        "Vary section/paragraph/sentence sizes and overlap; compare offsets and recall to labeled truth",
        "Meaning/provenance retained; no silent coverage loss or duplicate unsupported findings",
        "NOT RUN",
        "Existing automated boundary tests pass; broader human-labeled corpus not evaluated",
        "AI & evidence",
    ),
    (
        "Discovery",
        "Live bounded website legal-policy discovery",
        "Owned/approved public policy website and permission for capture/provider processing",
        "Submit website; inspect discovered policies, missing categories, redirects, robots and capture provenance",
        "Accessible relevant policies discovered without claiming exhaustive coverage",
        "BLOCKED",
        "Would create jobs/captured records and external requests",
        "Ingestion & discovery",
    ),
    (
        "Multi-model AI",
        "Live Gemini/Groq/OpenRouter structured analysis",
        "Authorized paid/quota budget and synthetic consented document",
        "Select each configured model; process once; inspect JSON, provider metadata, usage and failures",
        "No silent provider replacement; validated grounded findings and honest failures",
        "BLOCKED",
        "Paid/external AI requests explicitly not authorized",
        "AI & evidence",
    ),
    (
        "Evidence",
        "Independent semantic-support/exception precision and recall benchmark",
        "Human-labeled synthetic legal corpus and independent reviewers",
        "Blind-score supported/partial/unsupported/ambiguous outcomes against reviewer truth",
        "Calibrated precision/recall and exception coverage meet approved acceptance targets",
        "NOT RUN",
        "No labeled human benchmark or numeric acceptance threshold provided",
        "AI & evidence",
    ),
    (
        "Risk",
        "Independent High/Moderate/Low/Not Determinable rule review",
        "Legal/domain reviewer and labeled clauses",
        "Review documented rules including negation, exceptions, incomplete coverage and non-English source",
        "Transparent document-attention rules; no invented numerical risk/confidence or real-world practice claims",
        "NOT RUN",
        "Automated rule tests pass; independent risk validity not established",
        "Risk & multilingual",
    ),
    (
        "Chat",
        "Live document-grounded multilingual question answering",
        "Approved analyzed synthetic document and AI budget",
        "Ask English/Hindi/Hinglish/informal queries; open citations; ask absent/out-of-scope questions",
        "Exact original quotations, authorized citations and explicit selected-language abstention",
        "BLOCKED",
        "No account/document/AI production authorization",
        "AI & evidence",
    ),
    (
        "Language",
        "Production authenticated preference persistence across devices",
        "Approved test user and two device sessions",
        "Switch languages, navigate/reload, then sign in on second device",
        "PostgreSQL preference persists and original evidence text remains unchanged",
        "BLOCKED",
        "Authenticated preference/database writes not authorized",
        "Risk & multilingual",
    ),
    (
        "Translations",
        "Native-speaker fidelity and UI terminology review",
        "Hindi/Hinglish speakers and approved representative corpus",
        "Review negation, legal qualifications, labels and line wrapping in all screens/reports",
        "Accurate readable explanations; original authoritative quotes unmodified",
        "NOT RUN",
        "No native-speaker review performed",
        "Risk & multilingual",
    ),
    (
        "Comparison",
        "Live two-source comparison with source navigation",
        "Approved test user and two synthetic uploaded versions",
        "Compare sources, inspect additions/removals/repeated clauses and follow exact source references",
        "Owned exact-text changes; no fabricated semantic contradiction or unstated provisions",
        "BLOCKED",
        "Requires production account/source data",
        "Document comparison",
    ),
    (
        "Reports",
        "Production PDF/JSON/manifest generation and protected download",
        "Approved completed analysis and R2 write approval",
        "Generate each report/language, open citations/hash/coverage and attempt second-user access",
        "Correct persistent encrypted report; access isolated; translations never replace original quotes",
        "BLOCKED",
        "Would generate private reports and stored objects",
        "Reports & history",
    ),
    (
        "Deletion",
        "Production source/account deletion and R2 outbox retries",
        "Separate explicit destructive approval, backup and disposable test scope",
        "Delete only approved test source; simulate storage failure in staging; verify pending retries and preserved audit policy",
        "No cross-user deletion; durable eventual cleanup; no false physical-deletion success",
        "BLOCKED",
        "Destructive production testing prohibited",
        "Database & worker",
    ),
    (
        "Database",
        "Neon live FK/constraint/transaction and native FTS integrity",
        "Approved disposable PostgreSQL integration database",
        "Run isolated PostgreSQL integration tests, rollback scenarios and search/owner isolation checks",
        "Correct FK/index/transaction/FTS semantics; existing data untouched",
        "BLOCKED",
        "Production writes prohibited; no separate disposable PostgreSQL target authorized",
        "Database & worker",
    ),
    (
        "Migrations",
        "Production release migration execution / rollback drill",
        "Separate maintenance approval and verified backups",
        "Review revisions, apply to disposable clone, compare schema and test recovery",
        "Reviewed migrations preserve data and schema; tested restore procedure",
        "BLOCKED",
        "No production migration/rollback action authorized",
        "Database & worker",
    ),
    (
        "R2 storage",
        "Live R2 encrypted roundtrip, IAM and deletion scope",
        "Approved private test prefix/bucket and scoped R2 credentials",
        "Write synthetic object, read/hash/decrypt, test unauthorized principal, then separately approve deletion",
        "Private HTTPS encrypted objects; correct read/write/delete permissions and conditional creation",
        "BLOCKED",
        "R2 writes/deletion and credentials use not authorized",
        "Storage & deployment",
    ),
    (
        "R2 retention",
        "Version/lifecycle and backup erasure guarantees",
        "Approved test bucket with known lifecycle and backups",
        "Inspect version expiry and deletion semantics against disclosure; test recovery separately",
        "No unsupported claim of physical erasure; restore and retention verified",
        "BLOCKED",
        "No privileged bucket/backup inspection or changes authorized",
        "Storage & deployment",
    ),
    (
        "Worker",
        "Real supervised worker consumes and finishes durable jobs",
        "Approved staging worker/account/documents and AI budget",
        "Queue jobs; inspect leases/heartbeat/status; stop/restart worker; cancel safely",
        "No stale/duplicate persistence or automatic rebilling after lost lease",
        "BLOCKED",
        "Would mutate jobs and incur possible AI use",
        "Database & worker",
    ),
    (
        "Security",
        "Authenticated multi-tenant IDOR across every resource type",
        "Two approved disposable users and owned documents",
        "Swap IDs for source/section/job/analysis/finding/chat/report/compare; inspect neutral errors",
        "No cross-tenant content, existence, report or metadata leakage",
        "BLOCKED",
        "Production account/private-data access not authorized; isolated regression coverage exists",
        "Security hardening",
    ),
    (
        "Security",
        "Production rate-limit and brute-force behavior",
        "Separate approved staging/rate budget",
        "Issue bounded invalid login/recovery/provider requests while observing shared counters",
        "Consistent429 and anti-enumeration without lockout/credential leakage",
        "BLOCKED",
        "High-volume production requests and auth counter writes not authorized",
        "Security hardening",
    ),
    (
        "Security",
        "Deployed bundle/source-map comprehensive secret audit",
        "Approved complete deployment artifacts and secret-scanning policy",
        "Scan all deployed chunks/source maps against known secret patterns without publishing values",
        "No credentials or private document contents in public assets",
        "NOT RUN",
        "No exhaustive deployment artifact scan performed; public-page checks are narrower",
        "Security hardening",
    ),
    (
        "Security",
        "Independent penetration test and parser sandbox assessment",
        "Written scope and isolated environment",
        "Review parser limits, injection, OAuth linking, session fixation, SSRF, logging and recovery boundaries",
        "Independent security findings triaged against approved threat model",
        "NOT RUN",
        "No independent penetration test performed",
        "Security hardening",
    ),
    (
        "Accessibility",
        "Complete keyboard/screen-reader/200%-zoom journey",
        "Screen reader and assisted reviewer; approved account where needed",
        "Exercise auth/upload/summary/source/chat/report and dialogs with keyboard/AT/zoom",
        "Meaningful focus order, labels, announcements and source navigation across full journey",
        "NOT RUN",
        "Automated axe checks are not a complete human accessibility audit",
        "Frontend & navigation",
    ),
    (
        "Responsiveness",
        "Firefox/WebKit/tablet/landscape authenticated device matrix",
        "Installed alternate browsers and authorized synthetic account",
        "Run principal workflows at representative breakpoints and text zoom in each engine",
        "No clipped controls, unusable overflow or inaccessible navigation",
        "NOT RUN",
        "Current execution covers Chromium desktop/375px only",
        "Frontend & navigation",
    ),
    (
        "Performance",
        "Load/stress/concurrent analysis and backpressure benchmark",
        "Explicit load authorization, staging and approved AI budget/SLOs",
        "Ramp controlled concurrent uploads/jobs/chats; measure p50/p95/p99 and resource/queue behavior",
        "Meet agreed SLOs with no unsafe retries, corruption or cross-user leakage",
        "BLOCKED",
        "No load/stress/paid AI authorization or SLO provided",
        "Performance observations",
    ),
    (
        "Performance",
        "Render cold-start and long-duration availability SLO",
        "Approved monitoring window and stated SLO",
        "Measure multiple independently cold/warm windows and sleep/resume behavior",
        "Meet approved availability/latency targets; disclose free-tier operational limits",
        "NOT RUN",
        "Point-in-time GET samples do not establish long-term/cold-start performance",
        "Performance observations",
    ),
    (
        "Recovery",
        "Database/object/key backup restoration and disaster recovery",
        "Disposable clone, backup/key access and explicit recovery approval",
        "Restore database, encrypted objects and keys; verify references and representative reads",
        "Restore complete within agreed recovery targets; no accidental production overwrite",
        "BLOCKED",
        "Backup/recovery resources and permission not supplied",
        "Storage & deployment",
    ),
]


def manual_cases():
    for i, (feature, scenario, pre, steps, expected, status, reason, module) in enumerate(MANUAL, 1):
        add(
            f"PLAN-{i:03}",
            module,
            feature + ": " + scenario,
            pre,
            steps,
            "Authored synthetic fixtures only; never confidential documents or real user credentials",
            expected,
            reason,
            status,
            error=reason,
            fix="Obtain the stated approval/resources and execute in staging; retain current production restrictions",
            evidence="Safety scope + docs/REQUIREMENTS_AUDIT.md; related executed cases are separate rows",
            environment="Production restricted" if status == "BLOCKED" else "Planned / independent",
            kind="Performance / load"
            if module == "Performance observations"
            else "Security / acceptance"
            if module == "Security hardening"
            else "Acceptance / boundary / integration",
        )
    for i, (feature, scope) in enumerate(
        [
            ("OCR for scanned PDFs", "Current extractor rejects scan-only input; OCR explicitly deferred"),
            ("Human reviewer sign-off workflow", "Reviewer adjudication is planned P1 scope"),
            (
                "Trusted timestamps / court-admissibility certification",
                "Hash/capture metadata do not provide trusted timestamping or legal admissibility",
            ),
            (
                "Semantic contradiction alerts and continuous monitoring",
                "Current comparison is deterministic retained-text diff",
            ),
            ("Public MCP OAuth", "Private scoped read-only MCP exists; public OAuth is not implemented"),
            (
                "External legal research mode",
                "Current chat is document-only and external legal research is disabled",
            ),
        ],
        1,
    ):
        add(
            f"FUTURE-{i:02}",
            "Planned features",
            feature,
            "Feature implemented and accepted before execution",
            "Create acceptance plan when implementation enters scope",
            "No production inputs submitted",
            "Future feature meets separately agreed requirements",
            scope,
            "NOT IMPLEMENTED",
            severity="Low / P3",
            error="Explicitly deferred feature; not an executed failure",
            fix="Keep clearly labeled as planned; do not advertise as completed",
            evidence="docs/REQUIREMENTS_AUDIT.md; docs/ARCHITECTURE.md",
            environment="Planned / independent",
            kind="Future scope",
        )


def command_cases():
    for i, record in enumerate(load("checks.json"), 1):
        name = record["id"]
        add(
            f"CHECK-{i:02}",
            "Build & static checks",
            name,
            "Installed local project dependencies; existing configuration preserved",
            f"From {record['cwd']}: {record['command']}",
            "Maintained source and test files",
            "Process exits0 without lint/type errors",
            f"Exit code {record['exit_code']}",
            "PASS" if record["exit_code"] == 0 else "FAIL",
            error="None observed" if record["exit_code"] == 0 else "See command log",
            fix="Fix errors before release" if record["exit_code"] else "Retain CI gate",
            evidence="evidence/" + name + ".log | evidence/checks.json",
            kind="Static / regression",
            duration=record["duration_ms"],
        )
    log = read_log(E / "frontend-build.log")
    passed = bool(re.search(r"built in [0-9.]+s", log)) and not re.search(
        r"error TS[0-9]|failed to build|error during build", log, re.IGNORECASE
    )
    add(
        "CHECK-04",
        "Build & static checks",
        "Production TypeScript/Vite bundle",
        "Installed frontend dependencies",
        "From frontend run npm run build (tsc -b && vite build); inspect emitted assets and build result.",
        "Current maintained frontend source and Vite configuration",
        "Build completes without TypeScript/bundler errors",
        "Production asset bundle emitted; "
        + ("completion marker found" if passed else "completion missing/error found"),
        "PASS" if passed else "FAIL",
        evidence="evidence/frontend-build.log",
        kind="Build / regression",
    )


BUGS = [
    [
        "BUG-PROD-01",
        "SPA deep-link routing missing",
        "High / P1",
        "OPEN",
        "Direct GETs to /sign-in, /register, /forgot-password, /analyze, /library and /dashboard return404; client-side sign-in navigation renders.",
        "PROD-HTTP-13/14; PROD-UI-04..09",
        "Configure Vercel SPA fallback after any API routes; review generated vercel.json against actual project root. No automatic deployment authorized.",
        "Retest direct URLs, page refresh, verification/reset links and authenticated workspace URLs after approved redeployment.",
    ],
    [
        "BUG-PROD-02",
        "Production frontend CORS/auth integration fails",
        "Critical / P0",
        "OPEN",
        "Backend HTTP health/readiness pass; trusted Vercel Origin lacks Access-Control-Allow-Origin. Chromium credentialed fetch fails, profile/options fail, configured Google button remains disabled.",
        "PROD-HTTP-12; PROD-UI-10/11/13",
        "Correct ALLOWED_ORIGINS for the exact Vercel origin and review Render environment overrides. Current final browser traffic uses the /api/v1 prefix; preserve it. If choosing same-origin rewrite, qualify it separately.",
        "Retest browser /me401 and auth/options200, CORS allow/deny and Google-button enablement; full consent still needs authorization.",
    ],
    [
        "OBS-PROD-03",
        "Optional same-origin API rewrite unavailable",
        "Low / P3",
        "ARCHITECTURE DECISION",
        "Vercel /api/v1/health returns404; final browser traffic uses direct Render /api/v1 calls.",
        "PROD-HTTP-04",
        "No proxy is required if direct API mode is intentional and CORS is fixed. Otherwise add the external API rewrite before SPA fallback. Document the chosen contract.",
        "Retest only the selected architecture. This optional probe is not independently a release blocker.",
    ],
    [
        "BUG-HARDEN-04",
        "Frontend CSP absent on sampled HTML",
        "Medium / P2",
        "OPEN / HARDENING",
        "Production landing response has no Content-Security-Policy header; no exploit was attempted.",
        "SEC-HTTP-02",
        "Deploy a reviewed restrictive CSP through frontend hosting configuration; preserve required assets and OAuth navigation.",
        "Verify headers, browser behavior and report-only rollout as appropriate.",
    ],
    [
        "BUG-HARDEN-05",
        "Frontend anti-framing policy absent",
        "Medium / P2",
        "OPEN / HARDENING",
        "Sampled frontend HTML has neither X-Frame-Options nor a CSP frame-ancestors policy.",
        "SEC-HTTP-03",
        "Configure frame-ancestors or X-Frame-Options after product embedding requirements are reviewed.",
        "Inspect deployed headers; optionally test framing in an approved controlled environment.",
    ],
]


def styles(wb):
    def fmt(**kw):
        return wb.add_format({"font_name": "Aptos", "font_size": 10, **kw})

    return {
        "title": fmt(bg_color="#132D46", font_color="#FFFFFF", bold=True, font_size=20, valign="vcenter"),
        "subtitle": fmt(font_color="#476176", font_size=10, text_wrap=True, valign="vcenter"),
        "header": fmt(
            bg_color="#173F50",
            font_color="white",
            bold=True,
            text_wrap=True,
            valign="vcenter",
            border=1,
            border_color="#D5E0E7",
        ),
        "cell": fmt(valign="top", text_wrap=True, border=1, border_color="#E4EBF0"),
        "muted": fmt(font_color="#586B7A", text_wrap=True, valign="top"),
        "metric": fmt(
            bg_color="#EDF5F5",
            font_color="#173F50",
            bold=True,
            font_size=25,
            align="center",
            valign="vcenter",
            num_format="0",
        ),
        "percent": fmt(
            bg_color="#EDF5F5",
            font_color="#173F50",
            bold=True,
            font_size=25,
            align="center",
            valign="vcenter",
            num_format="0.0%",
        ),
        "label": fmt(bg_color="#DCEBEC", font_color="#173F50", bold=True, align="center", text_wrap=True),
        "section": fmt(bg_color="#DCEBEC", font_color="#173F50", bold=True, font_size=12),
        "warning": fmt(bg_color="#FFF0D2", font_color="#714B00", bold=True, text_wrap=True, valign="vcenter"),
        "danger": fmt(bg_color="#FDE7E7", font_color="#9E2020", bold=True, text_wrap=True, valign="vcenter"),
        "small": fmt(font_color="#586B7A", font_size=9, text_wrap=True, valign="top"),
        "link": fmt(font_color="#166D8F", underline=True, text_wrap=True, valign="top"),
    }


def init_sheet(ws, title, description, f):
    ws.hide_gridlines(2)
    ws.merge_range(0, 0, 1, 7, title, f["title"])
    ws.merge_range(2, 0, 2, 7, description, f["subtitle"])
    ws.set_row(0, 24)
    ws.set_row(1, 18)
    ws.set_row(2, 36)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)
    ws.set_paper(9)
    ws.set_margins(0.25, 0.25, 0.4, 0.4)
    ws.set_footer("&CVeriora QA | Confidentiality: synthetic/public evidence only | Page &P of &N")


def table_sheet(wb, name, rows, f):
    ws = wb.add_worksheet(name)
    init_sheet(
        ws,
        name,
        "Filter by status, environment and test type. PASS applies only to the exact executed scope. Local mocked acceptance is not live production acceptance.",
        f,
    )
    widths = [18, 25, 52, 48, 72, 55, 78, 78, 18, 19, 60, 65, 21, 75, 25, 30, 17, 25]
    for col, width in enumerate(widths):
        ws.set_column(col, col, width, f["cell"])
    ws.freeze_panes(4, 3)
    ws.set_row(3, 32)
    data = []
    for row in rows:
        data.append([str(v)[:32000] if isinstance(v, str) else v for v in row])
    if data:
        table_name = re.sub(r"[^A-Za-z]", "", name)
        if name == "All Test Cases":
            table_name = "AllCases"
        ws.add_table(
            3,
            0,
            3 + len(data),
            len(HEADERS) - 1,
            {
                "name": table_name,
                "columns": [{"header": h, "header_format": f["header"]} for h in HEADERS],
                "data": data,
                "style": "Table Style Medium 2",
            },
        )
        for row in range(4, 4 + len(data)):
            ws.set_row(row, 112)
        for status, color, font in [
            ("PASS", "#E3F3EC", "#155D3B"),
            ("FAIL", "#FCE4E4", "#9E2020"),
            ("BLOCKED", "#FFF0D2", "#805400"),
            ("NOT RUN", "#EBEFF3", "#526675"),
            ("NOT IMPLEMENTED", "#EDE6F7", "#614882"),
        ]:
            ws.conditional_format(
                4,
                8,
                3 + len(data),
                8,
                {
                    "type": "cell",
                    "criteria": "equal to",
                    "value": '"' + status + '"',
                    "format": wb.add_format(
                        {
                            "bg_color": color,
                            "font_color": font,
                            "bold": True,
                            "border": 1,
                            "border_color": "#E4EBF0",
                        }
                    ),
                },
            )
    ws.repeat_rows(0, 3)
    ws.autofit() if False else None
    return ws


def make_workbook():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "Veriora_Complete_Test_Report.xlsx"
    wb = xlsxwriter.Workbook(str(path), {"strings_to_formulas": False, "strings_to_urls": False})
    wb.set_properties(
        {
            "title": "Veriora Complete Test Report",
            "subject": "Executed local regression and read-only production QA",
            "author": "Veriora QA",
            "comments": "No production mutations, accounts, confidential documents or paid AI requests authorized.",
        }
    )
    wb.set_calc_mode("auto")
    f = styles(wb)
    dashboard = wb.add_worksheet("Test Summary & Dashboard")
    table_sheet(wb, "All Test Cases", ROWS, f)
    bugs = wb.add_worksheet("Failed Tests & Bugs")
    table_sheet(wb, "Security Tests", [r for r in ROWS if security(r[1] + r[2] + r[15])], f)
    table_sheet(
        wb,
        "API Tests",
        [r for r in ROWS if "API" in r[15] or r[0].startswith("PROD-HTTP") or r[1] == "API integration"],
        f,
    )
    table_sheet(
        wb,
        "Frontend & E2E Tests",
        [r for r in ROWS if r[0].startswith(("FE-", "E2E-", "PROD-UI-")) or "Frontend" in r[1]],
        f,
    )
    table_sheet(
        wb, "Performance Tests", [r for r in ROWS if "Performance" in r[1] or "Performance" in r[15]], f
    )
    evidence = wb.add_worksheet("Test Execution Evidence")
    counts = Counter(r[8] for r in ROWS)
    executed = counts["PASS"] + counts["FAIL"]
    init_sheet(
        dashboard,
        "Veriora | Complete Test Report",
        "Execution date "
        + NOW
        + " | Windows / Python 3.13 / Node / Chromium | Production: veriora.vercel.app + veriora-api.onrender.com",
        f,
    )
    dashboard.set_column("A:L", 12)
    dashboard.merge_range(
        "A5:L6",
        "RELEASE GATE: BLOCKED — production SPA routing and credentialed CORS/auth integration failures remain. Local suites pass. No complete live authenticated document/AI/R2 workflow was authorized.",
        f["danger"],
    )
    dashboard.set_row(4, 24)
    dashboard.set_row(5, 22)
    cards = [
        ("Total cases", "=COUNTA(AllCases[Test Case ID])", len(ROWS)),
        ("Executed", '=COUNTIF(AllCases[Status],"PASS")+COUNTIF(AllCases[Status],"FAIL")', executed),
        ("Passed", '=COUNTIF(AllCases[Status],"PASS")', counts["PASS"]),
        ("Failed", '=COUNTIF(AllCases[Status],"FAIL")', counts["FAIL"]),
        ("Blocked", '=COUNTIF(AllCases[Status],"BLOCKED")', counts["BLOCKED"]),
        ("Not run", '=COUNTIF(AllCases[Status],"NOT RUN")', counts["NOT RUN"]),
        ("Not implemented", '=COUNTIF(AllCases[Status],"NOT IMPLEMENTED")', counts["NOT IMPLEMENTED"]),
        (
            "Pass % (executed only)",
            '=IFERROR(COUNTIF(AllCases[Status],"PASS")/(COUNTIF(AllCases[Status],"PASS")+COUNTIF(AllCases[Status],"FAIL")),0)',
            counts["PASS"] / executed if executed else 0,
        ),
    ]
    for i, (label, formula, cached) in enumerate(cards):
        row = 7 + (i // 4) * 5
        col = (i % 4) * 3
        dashboard.merge_range(row, col, row, col + 2, label, f["label"])
        dashboard.merge_range(row + 1, col, row + 2, col + 2, "", f["percent"] if i == 7 else f["metric"])
        dashboard.write_formula(row + 1, col, formula, f["percent"] if i == 7 else f["metric"], cached)
    coverage = load("backend-coverage.json")["totals"]
    line = coverage["covered_lines"] / coverage["num_statements"]
    branch = coverage["covered_branches"] / coverage["num_branches"]
    dashboard.merge_range(
        "A18:L19",
        "Pass percentage excludes BLOCKED / NOT RUN / NOT IMPLEMENTED. Separate sheets are filtered views of the same inventory, not additional cases. Production GET timings are observations, not an SLA/load test. Optional proxy-path check failure is conditional under direct-API architecture.",
        f["warning"],
    )
    dashboard.merge_range("A21:F21", "Measured backend coverage", f["section"])
    dashboard.merge_range(
        "A22:D22",
        "Statements: " + str(coverage["covered_lines"]) + " / " + str(coverage["num_statements"]),
        f["cell"],
    )
    dashboard.write_number("E22", line, wb.add_format({"num_format": "0.00%", "bold": True}))
    dashboard.merge_range(
        "A23:D23",
        "Branches: " + str(coverage["covered_branches"]) + " / " + str(coverage["num_branches"]),
        f["cell"],
    )
    dashboard.write_number("E23", branch, wb.add_format({"num_format": "0.00%", "bold": True}))
    dashboard.merge_range(
        "A24:F25",
        "Coverage measured only for backend app via pytest-cov, including branches. Frontend code coverage was not measured. Local SQLite does not certify Neon concurrency/FTS or remote R2 behavior.",
        f["small"],
    )
    dashboard.write_row(27, 0, ["Environment", "Cases", "Executed", "Pass", "Fail", "Blocked"], f["header"])
    for j, env in enumerate(sorted({r[14] for r in ROWS}), 28):
        envrows = [r for r in ROWS if r[14] == env]
        c = Counter(r[8] for r in envrows)
        dashboard.write(j, 0, env, f["small"])
        dashboard.write_formula(j, 1, f"=COUNTIF(AllCases[Environment],A{j + 1})", f["cell"], len(envrows))
        for k, (statuses, cached) in enumerate(
            [
                (["PASS", "FAIL"], c["PASS"] + c["FAIL"]),
                (["PASS"], c["PASS"]),
                (["FAIL"], c["FAIL"]),
                (["BLOCKED"], c["BLOCKED"]),
            ],
            2,
        ):
            formula = "=" + "+".join(
                f'COUNTIFS(AllCases[Environment],A{j + 1},AllCases[Status],"{status}")' for status in statuses
            )
            dashboard.write_formula(j, k, formula, f["cell"], cached)
    dashboard.write_row(36, 0, ["Status", "Count"], f["header"])
    for j, status in enumerate(STATUSES, 37):
        dashboard.write(j, 0, status, f["cell"])
        dashboard.write_formula(j, 1, f"=COUNTIF(AllCases[Status],A{j + 1})", f["cell"], counts[status])
    chart = wb.add_chart({"type": "doughnut"})
    chart.add_series(
        {
            "name": "Test status",
            "categories": [dashboard.name, 37, 0, 41, 0],
            "values": [dashboard.name, 37, 1, 41, 1],
            "data_labels": {"percentage": True},
            "points": [
                {"fill": {"color": c}} for c in ["#288567", "#C74646", "#DAA744", "#9AA9B4", "#8972AC"]
            ],
        }
    )
    chart.set_title({"name": "Complete inventory by status"})
    chart.set_hole_size(65)
    chart.set_style(10)
    dashboard.insert_chart("H21", chart, {"x_scale": 0.85, "y_scale": 0.9})
    dashboard.merge_range(
        "A44:L46",
        "Key limits: no production account creation, form submissions, OAuth state initiation, private uploads/downloads/deletions, AI inference, schema changes, bucket mutations or load testing. Backend readiness runs SELECT1 only. Browser traffic is guarded. Real Google consent, SMTP delivery, Neon transactions and R2 roundtrip remain unverified.",
        f["warning"],
    )
    dashboard.merge_range("A48:L48", "Workbook navigation", f["section"])
    for i, name in enumerate(
        [
            "All Test Cases",
            "Failed Tests & Bugs",
            "Security Tests",
            "API Tests",
            "Frontend & E2E Tests",
            "Performance Tests",
            "Test Execution Evidence",
        ],
        49,
    ):
        dashboard.write_url(i, 0, "internal:'" + name + "'!A1", f["link"], name)
    dashboard.freeze_panes(7, 0)
    dashboard.set_print_scale(80)
    init_sheet(
        bugs,
        "Failed tests & defect tracking",
        "Five grouped observations; failure counts are individual assertions. Root-cause diagnoses are evidence-based hypotheses, not confirmed cloud-setting inspections. No production fix was applied.",
        f,
    )
    for col, width in enumerate([19, 42, 20, 29, 85, 48, 95, 85]):
        bugs.set_column(col, col, width, f["cell"])
    bugs.add_table(
        4,
        0,
        4 + len(BUGS),
        7,
        {
            "name": "Defects",
            "columns": [
                {"header": h, "header_format": f["header"]}
                for h in [
                    "Defect ID",
                    "Title",
                    "Severity / Priority",
                    "Disposition",
                    "Observed behavior",
                    "Failing case IDs",
                    "Recommended fix",
                    "Retest / acceptance",
                ]
            ],
            "data": BUGS,
            "style": "Table Style Medium 2",
        },
    )
    for j in range(5, 5 + len(BUGS)):
        bugs.set_row(j, 130)
    start = 12
    bugs.merge_range(start, 0, start, 7, "Individual failed test assertions (actual evidence)", f["section"])
    failures = [r for r in ROWS if r[8] == "FAIL"]
    bug_rows = [[r[0], r[1], r[2], r[9], r[7], r[10], r[11], r[13]] for r in failures]
    bugs.add_table(
        start + 2,
        0,
        start + 2 + len(bug_rows),
        7,
        {
            "name": "FailedAssertions",
            "columns": [
                {"header": h, "header_format": f["header"]}
                for h in [
                    "Case ID",
                    "Module",
                    "Scenario",
                    "Severity",
                    "Actual result",
                    "Error details",
                    "Recommended fix",
                    "Evidence",
                ]
            ],
            "data": bug_rows,
            "style": "Table Style Medium 2",
        },
    )
    for j in range(start + 3, start + 3 + len(bug_rows)):
        bugs.set_row(j, 115)
    bugs.freeze_panes(5, 2)
    write_evidence(evidence, wb, f, coverage)
    wb.close()
    summary = {
        "total": len(ROWS),
        "executed": executed,
        **{s: counts[s] for s in STATUSES},
        "pass_percentage_executed": counts["PASS"] / executed * 100 if executed else None,
        "backend_statement_coverage": line * 100,
        "backend_branch_coverage": branch * 100,
        "grouped_observations": len(BUGS),
        "created_utc": NOW,
    }
    (E / "report-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path, summary


def write_evidence(ws, wb, f, coverage):
    init_sheet(
        ws,
        "Execution evidence & limitations",
        "Raw outputs are embedded in summarized form and linked to local sidecars. Workbook remains readable independently; screenshots below are embedded, not external-image links.",
        f,
    )
    for col, width in enumerate([20, 75, 48, 80, 75, 65, 28, 105]):
        ws.set_column(col, col, width, f["cell"])
    ET.parse(E / "backend-junit.xml").findall(".//testcase")
    load("frontend-unit.json")
    pw = load("browser-e2e.json")["stats"]
    http = load("production-http.json")
    browser = load("production-browser.json")
    entries = [
        [
            "EV-01",
            "backend: python -m pytest tests -q --junitxml=../docs/testing/evidence/backend-junit.xml --cov=app --cov-branch --cov-report=json:../docs/testing/evidence/backend-coverage.json --cov-report=term-missing:skip-covered",
            "Isolated unit/API/security suite",
            "192 PASS,1 skipped; 102.92 seconds; statement82.87037%, branch69.50207%, combined79.80495%",
            "SQLite fixtures and mocked external boundaries; PostgreSQL opt-in disabled; no live AI/SMTP/Google/R2 inference",
            "evidence/backend-tests.log; backend-junit.xml; backend-coverage.json",
            DATE,
            read_log(E / "backend-tests.log")[-6500:],
        ],
        [
            "EV-02",
            "frontend: npm test -- --reporter=default --reporter=json --outputFile=../docs/testing/evidence/frontend-unit.json",
            "Vitest/jsdom",
            "22 PASS; 8 files; JSON numTotalTestSuites includes nested suites",
            "No frontend statement/branch coverage measured; mocks do not prove deployed integration",
            "evidence/frontend-unit.json; frontend-unit.log",
            DATE,
            read_log(E / "frontend-unit.log")[-4500:],
        ],
        [
            "EV-03",
            "frontend: npm run test:e2e",
            "Isolated FastAPI/worker/Vite + Chromium",
            f"{pw['expected']} passed; {pw['skipped']} skipped; {pw['unexpected']} unexpected; {pw['duration'] / 1000:.2f}s",
            "Synthetic Google JWT/JWKS and captured mail; no real consent or production writes; live account/AI scenario skipped",
            "evidence/browser-e2e.json; browser-e2e.log",
            DATE,
            read_log(E / "browser-e2e.log")[-6500:],
        ],
        [
            "EV-04",
            "frontend: npm run build",
            "TypeScript + Vite production assets",
            "Build completed (1757 modules); final asset bundle emitted",
            "No deployment or production configuration change implied",
            "evidence/frontend-build.log",
            DATE,
            read_log(E / "frontend-build.log")[-4000:],
        ],
        [
            "EV-05",
            "python scripts/qa_readonly_probe.py",
            "Bounded anonymous production HTTPS GETs",
            json.dumps(dict(Counter(r["status"] for r in http))),
            "No credentials/cookies; no OAuth start, upload, mutation or AI endpoint; readiness executes SELECT1 only",
            "evidence/production-http.json",
            DATE,
            json.dumps(http, ensure_ascii=False, indent=2)[:24000],
        ],
        [
            "EV-06",
            "node scripts/qa_readonly_browser.cjs",
            "Production public Chromium UI and CORS",
            json.dumps(dict(Counter(r["status"] for r in browser["records"]))),
            "Fresh browser; guarded network rejects mutations/OAuth/nonallowlisted host requests; no submissions; final run is authoritative",
            "evidence/production-browser.json; production-accessibility.json",
            DATE,
            json.dumps(browser, ensure_ascii=False, indent=2)[:26000],
        ],
    ]
    for check in load("checks.json"):
        log = read_log(E / (check["id"] + ".log"))
        entries.append(
            [
                "EV-CHECK-" + check["id"],
                check["cwd"]
                + ": "
                + ("python " if check["command"].startswith("-m ") else "")
                + check["command"],
                "Local static check",
                f"Exit{check['exit_code']}; {check['duration_ms']}ms",
                "No production operations",
                "evidence/checks.json; " + check["id"] + ".log",
                DATE,
                log or "No output; explicit captured exit code0",
            ]
        )
    entries.append(
        [
            "EV-SAFETY",
            "No production mutation methods were submitted",
            "Scope enforcement",
            f"Browser safety-blocked requests observed: {len(browser['blocked'])}",
            "No login/account creation, no Google-button click, no confidential docs, no paid inference, no bucket/DB mutations, no production settings changes",
            "scripts/qa_readonly_probe.py; scripts/qa_readonly_browser.cjs",
            DATE,
            "Production live account/document/AI/R2 tests remain BLOCKED. No native DB or bucket privileged access was attempted.",
        ]
    )
    entries.append(
        [
            "EV-SCOPE",
            "Repository and requirement review",
            "PRD/FRD/TRD/Design/architecture + routes/models/services/tests",
            "Local/deployed OpenAPI method inventories compared separately; source assertions linked per backend node",
            "Source inspection generates inventory/preconditions; it never sets PASS. PASS comes from executed test/HTTP/browser/check evidence only.",
            "docs/PRD.md; FRD.md; TRD.md; DESIGN.md; REQUIREMENTS_AUDIT.md; docs/openapi.json",
            DATE,
            "Case requirement trace is group-level navigation, not a claim that every requirement has full production acceptance.",
        ]
    )
    ws.add_table(
        4,
        0,
        4 + len(entries),
        7,
        {
            "name": "EvidenceTable",
            "columns": [
                {"header": h, "header_format": f["header"]}
                for h in [
                    "Evidence ID",
                    "Exact command / method",
                    "Scope",
                    "Actual result",
                    "Limits / safety",
                    "Artifact / source",
                    "Date UTC",
                    "Captured output / metadata",
                ]
            ],
            "data": entries,
            "style": "Table Style Medium 2",
        },
    )
    for row in range(5, 5 + len(entries)):
        ws.set_row(row, 145)
    start = 23
    ws.merge_range(
        start, 0, start, 7, "Backend coverage by maintained app module (measured, not inferred)", f["section"]
    )
    coverage_rows = []
    for file, value in load("backend-coverage.json")["files"].items():
        summary = value["summary"]
        lines = summary["num_statements"]
        branches = summary.get("num_branches", 0)
        coverage_rows.append(
            [
                file,
                summary["covered_lines"],
                lines,
                summary["covered_lines"] / lines if lines else None,
                summary.get("covered_branches", 0),
                branches,
                summary.get("covered_branches", 0) / branches if branches else None,
                "No executable branches"
                if not branches
                else "Local coverage; external operations may remain blocked",
            ]
        )
    columns = [
        {"header": h, "header_format": f["header"]}
        for h in [
            "App module",
            "Covered statements",
            "Total statements",
            "Statement coverage",
            "Covered branches",
            "Total branches",
            "Branch coverage",
            "Scope",
        ]
    ]
    columns[3]["format"] = wb.add_format({"num_format": "0.00%"})
    columns[6]["format"] = wb.add_format({"num_format": "0.00%"})
    ws.add_table(
        start + 2,
        0,
        start + 2 + len(coverage_rows),
        7,
        {
            "name": "CoverageByModule",
            "columns": columns,
            "data": coverage_rows,
            "style": "Table Style Medium 2",
        },
    )
    ws.merge_range(
        "A66:H68",
        "Production result: backend liveness/readiness and anonymous authorization pass; Vercel deep links and browser CORS/auth fail. R2 permission/roundtrip and real account/AI workflows remain blocked. Optional proxy probe404 is conditional under direct-API configuration. Missing frontend CSP/frame policy are hardening observations, not exploit proofs.",
        f["warning"],
    )
    # Embed bounded-size previews, retaining full image data for Excel zoom/export.
    import struct

    images = [
        ("production-desktop.png", 71, 0, "Production desktop landing"),
        ("production-mobile.png", 71, 3, "Production 375px landing"),
        ("summary-local.png", 112, 0, "Local synthetic Summary workspace"),
        ("workspace-local-mobile.png", 112, 3, "Local synthetic mobile evidence workspace"),
    ]
    for name, row, col, caption in images:
        image = E / name
        if not image.exists():
            continue
        ws.write(row, col, caption, f["section"])
        width, height = struct.unpack(">II", image.read_bytes()[16:24])
        scale = min(600 / width, 650 / height, 1)
        ws.insert_image(
            row + 2,
            col,
            str(image),
            {"x_scale": scale, "y_scale": scale, "object_position": 1, "description": caption},
        )
    ws.freeze_panes(5, 2)


def main():
    for source, target in [
        ("summary-desktop.png", "summary-local.png"),
        ("workspace-synthetic-mobile.png", "workspace-local-mobile.png"),
    ]:
        file = ROOT / "frontend/test-results" / source
        if file.exists():
            shutil.copyfile(file, E / target)
    backend_cases()
    frontend_cases()
    browser_cases()
    production_cases()
    derived_checks()
    manual_cases()
    command_cases()
    req = {
        "Authentication & sessions": "FR-AUTH-01..08 (group trace)",
        "Risk & multilingual": "FR-SUM-01/02; FR-LANG-01..05 (group trace)",
        "Document comparison": "FR-CMP-01",
        "Ingestion & discovery": "FR-ING-01..07; FR-URL-01..07 (group trace)",
        "AI & evidence": "FR-AI-01..16; FR-QA-01..04 (group trace)",
        "Reports & history": "FR-EXP-01..06 (group trace)",
        "Frontend & navigation": "FR-UI-01..06 (group trace)",
        "Security hardening": "FR-AUTH-03; TRD security",
        "Database & worker": "TRD PostgreSQL / jobs / migrations",
        "Storage & deployment": "TRD storage / docs/DEPLOYMENT.md",
        "MCP authorization": "TRD private MCP / authorization",
        "API integration": "FRD/API contract / docs/openapi.json",
        "Build & static checks": "TRD verification / build",
        "Planned features": "Requirements audit: explicit P1/P2/future scope",
        "Performance observations": "TRD operational/load release gates",
    }
    for row in ROWS:
        row[17] = row[17] or req.get(row[1], "FRD / requirements audit")
        if row[0] == "PROD-HTTP-04":
            row[9] = "Low / P3"
            row[7] += (
                "; conditional probe: current browser uses direct Render API; proxy is optional if deliberate"
            )
        if row[0] == "PROD-UI-16" and row[8] == "PASS":
            row[7] = (
                "Final browser evidence includes /api/v1/me and /api/v1/auth/options; no unprefixed calls observed. CORS failure is a separate case."
            )
    assert len({r[0] for r in ROWS}) == len(ROWS)
    path, summary = make_workbook()
    print(json.dumps({"workbook": str(path), **summary}, indent=2))


if __name__ == "__main__":
    main()
