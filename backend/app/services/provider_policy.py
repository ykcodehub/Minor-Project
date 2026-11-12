"""One consent boundary for API jobs, workers and every outbound retry."""

import time

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.providers.base import ProviderError
from app.providers.model_policy import requires_explicit_model


def names_for(user, payload):
    permissions = user.authorized_providers
    if permissions is None:
        return (
            list(
                dict.fromkeys(
                    [
                        payload.get("provider") or user.preferred_provider,
                        *payload.get("fallback_providers", []),
                    ]
                )
            )
            if payload.get("consent")
            else []
        )
    # Persistent consent is authoritative, including an empty list (revoke all).
    return [n for n in dict.fromkeys([user.preferred_provider, *permissions]) if n in permissions]


def providers_for(user, payload, factory=None, *, operation="analysis"):
    factory = factory or SessionLocal
    configs = {p["name"]: p for p in settings().providers()}
    names = names_for(user, payload)
    if not names:
        raise ProviderError("PROVIDER_PERMISSION_REVOKED")
    budget = {
        "deadline": time.monotonic() + settings().analysis_timeout_seconds,
        "calls": 0,
        "tokens": 0,
        "max_calls": settings().max_ai_calls_per_operation,
        "max_tokens": settings().max_ai_tokens_per_operation,
    }
    result = []
    dynamic_model_selected = False
    owner_id = user.id
    for name in names:
        if name not in configs or not configs[name]["key"] or not configs[name]["model"]:
            continue
        if operation == "analysis" and requires_explicit_model(name, configs[name]["model"]):
            dynamic_model_selected = True
            continue

        def authorized(name=name):
            with factory() as db:
                current = db.get(User, owner_id)
                return current is not None and name in names_for(current, payload)

        from app.services.provider_quota import hooks

        check, block = hooks(configs[name], factory)
        outage_check, outage_block = hooks(configs[name], factory, category="outage")
        result.append(
            {
                **configs[name],
                "authorize": authorized,
                "budget": budget,
                "operation": operation,
                "quota_check": check,
                "quota_block": block,
                "outage_check": outage_check,
                "outage_block": outage_block,
            }
        )
    if not result:
        if dynamic_model_selected:
            raise ProviderError("PROVIDER_EXPLICIT_MODEL_REQUIRED")
        raise ProviderError("PROVIDER_NOT_CONFIGURED")
    return result
