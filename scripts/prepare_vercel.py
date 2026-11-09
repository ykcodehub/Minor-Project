"""Generate reviewable Vercel configuration. Does not deploy or modify infrastructure."""

import argparse
import json
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit


def configuration(origin):
    target = urlsplit(origin)
    hostname = (target.hostname or "").rstrip(".").lower()
    local = hostname == "localhost" or hostname.endswith(".localhost")
    try:
        local = local or ip_address(hostname).is_loopback
    except ValueError:
        pass
    if (
        target.scheme != "https"
        or not target.hostname
        or target.username
        or target.password
        or target.query
        or target.fragment
        or target.path not in {"", "/"}
        or local
    ):
        raise ValueError(
            "Supply a public HTTPS backend origin without credentials or a path."
        )
    return {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "framework": "vite",
        "buildCommand": "npm run build",
        "outputDirectory": "dist",
        "rewrites": [
            {
                "source": "/api/:path*",
                "destination": origin.rstrip("/") + "/api/:path*",
            },
            {"source": "/((?!api(?:/|$)).*)", "destination": "/index.html"},
        ],
        "headers": [
            {
                "source": "/(.*)",
                "headers": [
                    {"key": "X-Content-Type-Options", "value": "nosniff"},
                    {"key": "Referrer-Policy", "value": "no-referrer"},
                    {"key": "X-Frame-Options", "value": "DENY"},
                    {
                        "key": "Content-Security-Policy",
                        "value": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
                    },
                ],
            }
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-origin", required=True)
    args = parser.parse_args()
    try:
        config = configuration(args.api_origin)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    target = Path(__file__).resolve().parents[1] / "frontend/vercel.json"
    target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(
        "Wrote frontend/vercel.json. Review routes/headers before deploying; no deployment performed."
    )


if __name__ == "__main__":
    main()
