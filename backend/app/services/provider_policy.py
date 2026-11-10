"""One consent boundary for API jobs, workers and every outbound retry."""

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.providers.base import ProviderError


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


def providers_for(user, payload, factory=None):
    factory = factory or SessionLocal
    configs = {p["name"]: p for p in settings().providers()}
    names = names_for(user, payload)
    if not names:
        raise ProviderError("PROVIDER_PERMISSION_REVOKED")
    budget = {
        "calls": 0,
        "tokens": 0,
        "max_calls": settings().max_ai_calls_per_operation,
        "max_tokens": settings().max_ai_tokens_per_operation,
    }
    result = []
    owner_id = user.id
    for name in names:
        if name not in configs or not configs[name]["key"] or not configs[name]["model"]:
            continue

        def authorized(name=name):
            with factory() as db:
                current = db.get(User, owner_id)
                return current is not None and name in names_for(current, payload)

        result.append({**configs[name], "authorize": authorized, "budget": budget})
    if not result:
        raise ProviderError("PROVIDER_NOT_CONFIGURED")
    return result
