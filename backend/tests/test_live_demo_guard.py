"""The live-test harness must stop globally on uncertainty, not recover as a finding."""

import runpy
from pathlib import Path

import httpx
import pytest

from app.providers.base import configured_provider
from app.services.analysis import CandidateBatch

HARNESS = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/verify_demo_live.py"))


@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(400, json={"error": {"message": "PRIVATE MUST NOT LEAK"}}), "LIVE_PROVIDER_HTTP_400"),
        (httpx.Response(200, json={"usage": {"cost": 1}}), "ZERO_COST_RESPONSE_UNCONFIRMED"),
        (httpx.Response(200, json={"usage": {}}), "ZERO_COST_RESPONSE_UNCONFIRMED"),
    ],
)
def test_live_gate_errors_abort_adapter_without_retry_or_partial_recovery(monkeypatch, response, code):
    calls = []

    def post(*args, **kwargs):
        calls.append(True)
        HARNESS["check_live_response"](response, {})

    monkeypatch.setattr(httpx.Client, "post", post)
    monkeypatch.setattr("app.providers.base.time.sleep", lambda _: pytest.fail("No retry permitted"))
    with pytest.raises(HARNESS["LiveGateError"], match=code):
        configured_provider({"name": "gemini", "model": "synthetic", "key": "synthetic"}).generate(
            "synthetic", "synthetic", CandidateBatch, "candidate_generation"
        )
    assert len(calls) == 1


def test_exact_zero_price_response_is_accepted_without_copying_source_text():
    call = {}
    HARNESS["check_live_response"](
        httpx.Response(
            200,
            json={
                "model": "test/structured:free",
                "usage": {"cost": 0},
                "choices": [{"finish_reason": "stop", "message": {"content": "PRIVATE"}}],
            },
        ),
        call,
    )
    assert call["usage"]["cost"] == 0 and "PRIVATE" not in str(call)
