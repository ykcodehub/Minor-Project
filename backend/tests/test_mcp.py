"""Private MCP protocol/security regression tests; no external client or model calls."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

pytest.importorskip("mcp", reason="Install the optional mcp extra to test protocol integration")

from app import mcp_server
from app.config import settings
from app.db import SessionLocal
from app.mcp_server import TOOLS, create_app
from app.models import Analysis, AnalysisSource, AuditEvent, Finding, Job, Source, User, now
from app.worker import run_once

TOKEN = "synthetic-mcp-token-" + "x" * 48


def _register(client, email="owner@example.com"):
    from test_api import register

    return register(client, email=email)["id"]


def _configure(monkeypatch, user_id, scopes=TOOLS):
    monkeypatch.setenv("MCP_BEARER_TOKEN", TOKEN)
    monkeypatch.setenv("MCP_USER_ID", user_id)
    monkeypatch.setenv("MCP_SCOPES", ",".join(sorted(scopes)))
    monkeypatch.setenv("MCP_TOKEN_EXPIRES_AT", (now() + timedelta(minutes=5)).isoformat())


def _rpc(client, method, params=None, ident=1):
    params = {
        **(params or {}),
        "_meta": {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
        },
    }
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}},
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/json, text/event-stream",
            "Mcp-Protocol-Version": "2026-07-28",
            "Mcp-Method": method,
            **({"Mcp-Name": params["name"]} if "name" in params else {}),
        },
    )


def _call(client, name, arguments=None):
    response = _rpc(client, "tools/call", {"name": name, "arguments": arguments or {}})
    assert response.status_code == 200, response.text
    return response.json()


def _upload(client, text="Consent is required before data sharing."):
    response = client.post("/api/v1/sources/text", json={"name": "Policy.txt", "text": text})
    assert response.status_code == 202, response.text
    assert run_once()
    return response.json()["source_id"]


def test_mcp_requires_strong_expiring_explicit_configuration(client, monkeypatch):
    user_id = _register(client)
    _configure(monkeypatch, user_id)
    monkeypatch.setenv("MCP_BEARER_TOKEN", "short")
    with pytest.raises(RuntimeError, match="strong token"):
        create_app()
    monkeypatch.setenv("MCP_BEARER_TOKEN", TOKEN)
    monkeypatch.setenv("MCP_TOKEN_EXPIRES_AT", (now() - timedelta(minutes=1)).isoformat())
    with pytest.raises(RuntimeError, match="future"):
        create_app()
    _configure(monkeypatch, user_id, {"delete_document"})
    with pytest.raises(RuntimeError, match="scopes"):
        create_app()


def test_mcp_protocol_lists_only_read_tools_and_requires_bearer(client, monkeypatch):
    user_id = _register(client)
    _configure(monkeypatch, user_id)
    with TestClient(create_app(), base_url="http://localhost:8001") as mcp:
        rejected = mcp.post("/mcp", json={})
        assert rejected.status_code == 401
        assert rejected.headers["www-authenticate"] == "Bearer"
        response = _rpc(mcp, "tools/list")
        assert response.status_code == 200, response.text
        names = {tool["name"] for tool in response.json()["result"]["tools"]}
        assert names == TOOLS
        payload = _call(mcp, "list_my_documents")
        assert not payload["result"].get("isError", False), payload
        assert (
            mcp.post("/mcp", content=b"x" * 65537, headers={"Authorization": "Bearer " + TOKEN}).status_code
            == 413
        )


def test_mcp_tool_scope_is_enforced_and_audited(client, monkeypatch):
    user_id = _register(client)
    source_id = _upload(client)
    _configure(monkeypatch, user_id, {"list_my_documents"})
    with TestClient(create_app(), base_url="http://localhost:8001") as mcp:
        payload = _call(mcp, "get_document_sections", {"source_id": source_id})
        assert payload["result"]["isError"] is True
        assert "Consent is required" not in str(payload)
    with SessionLocal() as db:
        assert db.scalar(
            select(AuditEvent).where(AuditEvent.actor_id == user_id, AuditEvent.action == "mcp.denied")
        )


def test_mcp_rejects_other_users_expired_sources_and_disabled_account(client, monkeypatch):
    first_user = _register(client)
    first = _upload(client)
    _configure(monkeypatch, first_user)
    second_user = _register(client, "other@example.com")
    other = _upload(client, "Private second-user terms.")
    with TestClient(create_app(), base_url="http://localhost:8001") as mcp:
        assert "Consent is required" in str(_call(mcp, "get_document_sections", {"source_id": first}))
        denied = _call(mcp, "get_document_sections", {"source_id": other})
        assert denied["result"]["isError"] is True
        assert "Private second-user" not in str(denied)
        with SessionLocal() as db:
            db.get(Source, first).expires_at = now() - timedelta(seconds=1)
            db.commit()
        assert _call(mcp, "get_document_sections", {"source_id": first})["result"]["isError"] is True
        listing = _call(mcp, "list_my_documents")
        assert first not in str(listing) and other not in str(listing)
        with SessionLocal() as db:
            db.get(User, first_user).verified_at = None
            db.commit()
        assert _rpc(mcp, "tools/list").status_code == 401
    assert first_user != second_user


def test_mcp_preserves_evidence_status_and_uses_shared_analysis_ownership(client, monkeypatch):
    user_id = _register(client)
    source_id = _upload(client)
    with SessionLocal() as db:
        job = Job(owner_id=user_id, kind="analysis", state="COMPLETED", stage="COMPLETED")
        db.add(job)
        db.flush()
        analysis = Analysis(
            owner_id=user_id,
            job_id=job.id,
            coverage={"sections_processed": 1},
            limitations=["Synthetic regression fixture"],
        )
        db.add(analysis)
        db.flush()
        analysis_id = analysis.id
        db.add(AnalysisSource(analysis_id=analysis.id, source_id=source_id))
        finding = Finding(
            analysis_id=analysis.id,
            data={
                "category": "CONSENT",
                "statement": "Consent is required.",
                "support_status": "AMBIGUOUS",
                "citations": [],
                "verification": {"rationale": "Needs review."},
            },
        )
        db.add(finding)
        db.flush()
        finding_id = finding.id
        db.commit()
    _configure(monkeypatch, user_id)
    with TestClient(create_app(), base_url="http://localhost:8001") as mcp:
        payload = _call(mcp, "get_evidence_passport", {"analysis_id": analysis_id, "finding_id": finding_id})
        assert not payload["result"].get("isError", False), payload
        assert "AMBIGUOUS" in str(payload)
        assert "SUPPORTED" not in str(payload)
        assert "sections_processed" in str(_call(mcp, "get_analysis_report", {"analysis_id": analysis_id}))
        assert "Consent is required" in str(
            _call(mcp, "search_document_clauses", {"analysis_id": analysis_id, "query": "consent"})
        )
        denied = _call(
            mcp, "get_evidence_passport", {"analysis_id": analysis_id, "finding_id": "other-finding"}
        )
        assert denied["result"]["isError"] is True


def test_mcp_runtime_token_expiry_and_production_refusal(client, monkeypatch):
    user_id = _register(client)
    _configure(monkeypatch, user_id)
    app = create_app()
    future = now() + timedelta(minutes=6)
    monkeypatch.setattr(mcp_server, "now", lambda: future)
    with TestClient(app, base_url="http://localhost:8001") as mcp:
        assert _rpc(mcp, "tools/list").status_code == 401
    monkeypatch.setattr(mcp_server, "now", now)
    _configure(monkeypatch, user_id)
    monkeypatch.setattr(settings(), "environment", "production")
    with pytest.raises(RuntimeError, match="disabled in production"):
        create_app()
