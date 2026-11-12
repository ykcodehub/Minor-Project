"""Fail-closed capability checks for explicit OpenRouter models; no inference probes.

Catalog metadata is cached briefly, never used to authorize providers or select a
replacement model. A catalog failure cannot silently enable a dynamic router.
"""

import threading
import time
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx

_cache = {}
_lock = threading.Lock()
_endpoint_cache = {}
DYNAMIC_MODELS = {"openrouter/free", "openrouter/auto", "openrouter/bodybuilder"}


def requires_explicit_model(provider_name, model):
    return provider_name == "openrouter" and (
        model in DYNAMIC_MODELS or model.startswith(("@", "openrouter/"))
    )


def eligible_endpoint(model):
    """Fresh routing health, not a guarantee that the next inference succeeds."""
    from app.providers.base import ProviderError

    with _lock:
        cached = _endpoint_cache.get(model)
        if cached and cached[0] > time.monotonic():
            entries = cached[1]
        else:
            try:
                with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
                    response = client.get(
                        "https://openrouter.ai/api/v1/models/" + quote(model, safe="/:") + "/endpoints"
                    )
                response.raise_for_status()
                entries = response.json()["data"]["endpoints"]
                if not isinstance(entries, list):
                    raise TypeError("Invalid endpoint metadata")
                if len(_endpoint_cache) >= 30:
                    _endpoint_cache.clear()
                _endpoint_cache[model] = (time.monotonic() + 15, entries)
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raise ProviderError("PROVIDER_CAPABILITIES_UNAVAILABLE") from None
    for entry in entries:
        if entry.get("status") != 0:
            continue
        parameters = set(entry.get("supported_parameters") or [])
        if not {"structured_outputs", "max_tokens", "response_format"}.issubset(parameters):
            continue
        if not entry.get("tag"):
            continue
        if model.endswith(":free"):
            try:
                pricing = entry.get("pricing") or {}
                if any(Decimal(str(pricing.get(key, "-1"))) != 0 for key in ("prompt", "completion")):
                    continue
                if Decimal(str(pricing.get("request", "0"))) != 0:
                    continue
            except InvalidOperation:
                continue
        return entry
    raise ProviderError("PROVIDER_NO_HEALTHY_ENDPOINT")


def model_info(model):
    from app.providers.base import ProviderError

    with _lock:
        cached = _cache.get(model)
        if cached and cached[0] > time.monotonic():
            if cached[1] is None:
                raise ProviderError("PROVIDER_CAPABILITIES_UNAVAILABLE")
            return cached[1]
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
                response = client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            entries = response.json()["data"]
            if not isinstance(entries, list):
                raise TypeError("Invalid catalog")
            # Bound memory and avoid one catalog GET per model/window.
            _cache.clear()
            expires = time.monotonic() + 300
            for entry in entries[:2000]:
                if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                    _cache[entry["id"]] = (
                        expires,
                        {
                            key: entry[key]
                            for key in (
                                "id",
                                "context_length",
                                "supported_parameters",
                                "reasoning",
                                "top_provider",
                                "pricing",
                            )
                            if key in entry
                        },
                    )
            if model not in _cache:
                raise ProviderError("PROVIDER_MODEL_UNAVAILABLE")
            return _cache[model][1]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            _cache[model] = (time.monotonic() + 30, None)
            raise ProviderError("PROVIDER_CAPABILITIES_UNAVAILABLE") from None


def apply_policy(provider, payload):
    """Validate capability and tighten budgets before full-envelope accounting."""
    from app.providers.base import ProviderError

    if provider.name == "gemini":
        if provider.model in {"gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite"}:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
        elif provider.model in {"gemini-2.5-flash", "gemini-2.5-flash-lite"}:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        return
    if provider.name != "openrouter":
        return
    if requires_explicit_model(provider.name, provider.model):
        raise ProviderError("PROVIDER_EXPLICIT_MODEL_REQUIRED")
    info = model_info(provider.model)
    parameters = set(info.get("supported_parameters") or [])
    if "structured_outputs" not in parameters or "max_tokens" not in parameters:
        raise ProviderError("PROVIDER_MODEL_INCOMPATIBLE")
    if "temperature" not in parameters:
        payload.pop("temperature", None)
    reasoning = info.get("reasoning") or {}
    # Mandatory reasoning cannot safely share these compact JSON allowances.
    # Reject before billing rather than pretending exclude=true disables it.
    if reasoning.get("mandatory"):
        raise ProviderError("PROVIDER_REASONING_INCOMPATIBLE")
    if "reasoning" in parameters:
        payload["reasoning"] = {"enabled": False}
    elif reasoning.get("default_enabled"):
        raise ProviderError("PROVIDER_REASONING_INCOMPATIBLE")
    context = info.get("context_length")
    output = (info.get("top_provider") or {}).get("max_completion_tokens")
    if type(context) is not int or context <= 0:
        raise ProviderError("PROVIDER_MODEL_INCOMPATIBLE")
    provider.request_tokens = min(provider.request_tokens, context)
    provider.context_tokens = context
    if type(output) is int and output > 0:
        provider.max_output_tokens = min(provider.max_output_tokens, output)
        payload["max_tokens"] = min(payload["max_tokens"], output)
    endpoint = eligible_endpoint(provider.model)
    if "reasoning" in payload and "reasoning" not in endpoint["supported_parameters"]:
        raise ProviderError("PROVIDER_REASONING_INCOMPATIBLE")
    payload["provider"]["only"] = [endpoint["tag"]]
    if provider.model.endswith(":free"):
        payload["provider"]["max_price"] = {"prompt": 0, "completion": 0, "request": 0}
    endpoint_context = endpoint.get("context_length")
    if type(endpoint_context) is int and endpoint_context > 0:
        provider.request_tokens = min(provider.request_tokens, endpoint_context)
    endpoint_output = endpoint.get("max_completion_tokens")
    if type(endpoint_output) is int and endpoint_output > 0:
        provider.max_output_tokens = min(provider.max_output_tokens, endpoint_output)
        payload["max_tokens"] = min(payload["max_tokens"], endpoint_output)
