"""Bounded public GET checks only; never authenticate, submit forms, or call AI."""

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/testing/evidence/production-http.json"
FRONT = "https://veriora.vercel.app"
API = "https://veriora-api.onrender.com"


def main():
    records = []
    cases = [
        ("PROD-HTTP-01", "Backend liveness", API + "/api/v1/health", 200, None),
        ("PROD-HTTP-02", "Backend database readiness (SELECT 1 only)", API + "/api/v1/ready", 200, None),
        ("PROD-HTTP-03", "Public frontend HTML", FRONT + "/", 200, None),
        ("PROD-HTTP-04", "Vercel same-origin API liveness rewrite", FRONT + "/api/v1/health", 200, None),
        ("PROD-HTTP-05", "Anonymous current-user endpoint rejects access", API + "/api/v1/me", 401, None),
        ("PROD-HTTP-06", "Anonymous source listing rejects access", API + "/api/v1/sources", 401, None),
        ("PROD-HTTP-07", "Anonymous dashboard rejects access", API + "/api/v1/dashboard", 401, None),
        (
            "PROD-HTTP-08",
            "Anonymous document download rejects access",
            API + "/api/v1/sources/qa-nonexistent/original",
            401,
            None,
        ),
        (
            "PROD-HTTP-09",
            "Public authentication options return safe configuration",
            API + "/api/v1/auth/options",
            200,
            None,
        ),
        ("PROD-HTTP-10", "Public OpenAPI schema", API + "/openapi.json", 200, None),
        (
            "PROD-HTTP-11",
            "Untrusted Origin is not reflected in CORS",
            API + "/api/v1/health",
            200,
            "https://qa-untrusted.invalid",
        ),
        ("PROD-HTTP-12", "Trusted frontend Origin is allowed by CORS", API + "/api/v1/health", 200, FRONT),
        ("PROD-HTTP-13", "Sign-in SPA deep link", FRONT + "/sign-in", 200, None),
        ("PROD-HTTP-14", "Library SPA deep link", FRONT + "/library", 200, None),
        (
            "PROD-HTTP-15",
            "Anonymous analysis retrieval rejects access",
            API + "/api/v1/analyses/qa-nonexistent",
            401,
            None,
        ),
    ]
    # Only authenticated read routes from the reviewed local contract; never OAuth GETs.
    schema = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    existing = {case[2] for case in cases}
    for route, methods in schema["paths"].items():
        if "get" not in methods or not route.startswith("/api/v1/") or "/auth/" in route:
            continue
        url = API + re.sub(r"\{[^}]+\}", "qa-nonexistent", route)
        if url in existing or route in {"/api/v1/health", "/api/v1/ready"}:
            continue
        cases.append(
            (
                f"PROD-AUTH-GET-{len(cases) - 14:03}",
                "Anonymous private endpoint rejects access: GET " + route,
                url,
                401,
                None,
            )
        )
        existing.add(url)
    with httpx.Client(
        timeout=httpx.Timeout(45, connect=15), follow_redirects=False, trust_env=True
    ) as client:
        for ident, scenario, url, expected, origin in cases:
            start = time.perf_counter()
            rec = {
                "id": ident,
                "scenario": scenario,
                "url": url,
                "expected": expected,
                "method": "GET",
                "date": datetime.now(UTC).isoformat(),
                "input": "Anonymous, no cookies; no form submissions",
                "origin": origin,
            }
            try:
                response = client.get(
                    url,
                    headers={
                        "User-Agent": "Veriora-ReadOnly-QA/1.0",
                        **({"Origin": origin} if origin else {}),
                    },
                )
                rec.update(
                    http_status=response.status_code,
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                    content_type=response.headers.get("content-type", ""),
                    bytes=len(response.content),
                )
                rec["headers"] = {
                    key: response.headers[key]
                    for key in (
                        "content-security-policy",
                        "strict-transport-security",
                        "x-content-type-options",
                        "x-frame-options",
                        "referrer-policy",
                        "cache-control",
                        "access-control-allow-origin",
                        "access-control-allow-credentials",
                        "x-request-id",
                    )
                    if key in response.headers
                }
                rec["status"] = "PASS" if response.status_code == expected else "FAIL"
                rec["actual"] = f"HTTP {response.status_code}; {rec['content_type']}; {rec['duration_ms']} ms"
                try:
                    data = response.json()
                except ValueError:
                    data = None
                if (
                    ident in {"PROD-HTTP-01", "PROD-HTTP-04", "PROD-HTTP-11", "PROD-HTTP-12"}
                    and response.status_code == 200
                ) and (not isinstance(data, dict) or data.get("status") != "ok"):
                    rec["status"] = "FAIL"
                    rec["actual"] += "; expected liveness JSON absent (possible SPA rewrite fallback)"
                if (
                    ident == "PROD-HTTP-02"
                    and response.status_code == 200
                    and (not isinstance(data, dict) or data.get("database") != "connected")
                ):
                    rec["status"] = "FAIL"
                    rec["actual"] += "; database readiness JSON absent"
                if ident == "PROD-HTTP-09" and response.status_code == 200:
                    if isinstance(data, dict):
                        rec["auth_options"] = {
                            "google_enabled": data.get("google"),
                            "email_enabled": data.get("email"),
                            "google_login_https": str(data.get("google_login_url", "")).startswith(
                                "https://"
                            ),
                        }
                    if (
                        not isinstance(data, dict)
                        or not isinstance(data.get("google"), bool)
                        or not isinstance(data.get("email"), bool)
                    ):
                        rec["status"] = "FAIL"
                        rec["actual"] += "; invalid authentication options contract"
                if ident == "PROD-HTTP-10" and response.status_code == 200:
                    if isinstance(data, dict) and "paths" in data:
                        rec["operations"] = [
                            method.upper() + " " + path
                            for path, methods in data["paths"].items()
                            for method in methods
                            if method in {"get", "post", "patch", "delete", "put"}
                        ]
                    else:
                        rec["status"] = "FAIL"
                        rec["actual"] += "; OpenAPI contract absent"
                if origin:
                    allowed = response.headers.get("access-control-allow-origin")
                    if ("untrusted" in origin and allowed is not None) or (
                        origin == FRONT and allowed != FRONT
                    ):
                        rec["status"] = "FAIL"
                        rec["actual"] += "; CORS Origin expectation failed"
                if isinstance(data, dict):
                    rec["public_fields"] = {
                        k: data[k]
                        for k in ("status", "database", "version", "code")
                        if k in data and isinstance(data[k], (str, bool, int))
                    }
            except httpx.HTTPError as error:
                rec.update(
                    status="BLOCKED",
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                    actual="Transport unavailable: " + type(error).__name__,
                    error=type(error).__name__,
                )
            records.append(rec)
            OUT.write_text(json.dumps(records, indent=2), encoding="utf-8")
            print(f"{ident}: {rec['status']}; {rec['actual']}", flush=True)
    print("Public GET checks finished; no authentication, mutation or AI request performed.")


if __name__ == "__main__":
    main()
