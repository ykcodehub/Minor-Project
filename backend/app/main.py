import logging


class AuthQueryRedaction(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args = list(record.args)
            if isinstance(args[2], str) and args[2].startswith("/api/v1/auth/"):
                args[2] = args[2].split("?", 1)[0]
                record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(AuthQueryRedaction())

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api import analyses, auth, comparisons, dashboard, documents
from app.config import settings

app = FastAPI(title="Veriora", version="2.0.0")
origins = [origin.strip() for origin in settings().allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    expose_headers=["X-Total-Count", "X-Request-ID", "X-Report-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > settings().max_upload_bytes + 1024 * 1024):
        return JSONResponse(
            {
                "code": "REQUEST_TOO_LARGE",
                "message": "Request exceeds the configured limit.",
                "request_id": request.state.request_id,
            },
            status_code=413,
        )
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin not in origins:
            return JSONResponse(
                {
                    "code": "ORIGIN_REJECTED",
                    "message": "Request origin is not permitted.",
                    "request_id": request.state.request_id,
                },
                status_code=403,
            )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if request.url.path == "/api/v1/auth/google/callback":
        reason = getattr(exc, "public_code", "OAUTH_CALLBACK_REJECTED")
        # Only application-owned reason codes and the request ID enter logs.
        logging.getLogger("uvicorn.error").warning(
            "OAuth callback rejected reason=%s request_id=%s", reason, request.state.request_id
        )
        if "text/html" in request.headers.get("accept", ""):
            response = RedirectResponse(settings().public_url + "/sign-in?oauth=failed", status_code=303)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            auth.clear_google_cookie(response)
            return response
    return JSONResponse(
        {
            "code": getattr(exc, "public_code", f"HTTP_{exc.status_code}"),
            "message": str(exc.detail),
            "request_id": request.state.request_id,
        },
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        {
            "code": "INVALID_REQUEST",
            "message": "Check the supplied fields and limits.",
            "request_id": request.state.request_id,
            "details": [
                {"field": ".".join(str(x) for x in e["loc"]), "type": e["type"]} for e in exc.errors()
            ],
        },
        status_code=422,
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Do not return raw exception text: parsers and providers may include source content or keys.
    return JSONResponse(
        {
            "code": "INTERNAL_ERROR",
            "message": "The operation failed. Please try again later.",
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
        status_code=500,
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    return JSONResponse(
        {
            "code": "DATABASE_ERROR",
            "message": "Database operation failed. Retry later or contact the administrator.",
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
        status_code=503,
    )


for router in (auth.router, documents.router, analyses.router, comparisons.router, dashboard.router):
    app.include_router(router, prefix="/api/v1")


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/v1/ready")
def ready():
    from sqlalchemy import text

    from app.db import SessionLocal

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        from app.runtime import worker_ready

        if not worker_ready():
            return JSONResponse(
                {"status": "unavailable", "database": "connected", "worker": "starting_or_stalled"},
                status_code=503,
            )
        return {"status": "ready", "database": "connected"}
    except SQLAlchemyError:
        return JSONResponse({"status": "unavailable", "database": "unavailable"}, status_code=503)
