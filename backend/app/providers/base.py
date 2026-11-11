"""Bounded HTTP model adapters. No document bodies or secrets enter error messages."""

from __future__ import annotations

import json
import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.providers.diagnostics import (
    error_details,
    json_content,
    strict_wire_schema,
    structured_retry_delay,
    validation_details,
)

LOW_REASONING_ROLES = frozenset(
    {
        "semantic_verification",
        "context_indexing",
        "explanation_translation",
        "translation_verification",
        "question_answering",
        "multilingual_retrieval",
    }
)


class ProviderError(RuntimeError):
    def __init__(self, code: str, *, calls: list[dict] | None = None):
        self.code = code
        self.model_calls = calls or []
        super().__init__(code)


def gemini_schema(schema: dict) -> dict:
    """Translate bounded Pydantic schemas to a smaller provider-compatible JSON schema.

    Local validation retains every length/range bound removed from the wire schema.
    Gemini can reject complex nested bounded arrays with a bare INVALID_ARGUMENT.
    """
    definitions = schema.get("$defs", {})

    def visit(value, depth=0):
        if depth > 30:
            raise ProviderError("PROVIDER_SCHEMA_TOO_COMPLEX")
        if isinstance(value, list):
            return [visit(item, depth + 1) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            reference = value["$ref"]
            if not reference.startswith("#/$defs/") or reference.split("/")[-1] not in definitions:
                raise ProviderError("PROVIDER_SCHEMA_UNSUPPORTED")
            return visit(definitions[reference.split("/")[-1]], depth + 1)
        return {
            key: visit(item, depth + 1)
            for key, item in value.items()
            if key
            not in {"$defs", "title", "minimum", "maximum", "minLength", "maxLength", "maxItems", "minItems"}
        }

    return visit(schema)


@dataclass
class ModelProvider:
    name: str
    model: str
    key: str = field(repr=False)
    on_attempt: Callable[[dict], None] | None = field(default=None, repr=False)
    authorize: Callable[[], bool] | None = field(default=None, repr=False)
    budget: dict | None = field(default=None, repr=False)
    checkpoint: Any = field(default=None, repr=False)
    quota_check: Callable | None = field(default=None, repr=False)
    quota_block: Callable | None = field(default=None, repr=False)
    operation: str = "analysis"
    context_tokens: int | None = None
    request_tokens: int = 24000
    max_output_tokens: int = 8192
    max_payload_bytes: int = 256000
    timeout: float = 40.0
    retries: int = 2
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None

    def request(self, system: str, prompt: str, schema: dict) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def request_usage(self, payload: dict) -> dict:
        """One conservative wire estimate for splitting and the final outbound guard.

        Router IDs have no fixed selected-model context. The application request
        cap still applies; an explicit known model context can only tighten it.
        """
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        output = payload.get("max_tokens", payload.get("generationConfig", {}).get("maxOutputTokens", 0))
        input_tokens = int(self.count_tokens(encoded) * 1.2) + 256
        return {
            "estimated_input_tokens": input_tokens,
            "reserved_output_tokens": output,
            "estimated_request_tokens": input_tokens + output,
            "payload_bytes": len(encoded.encode("utf-8")),
            "request_token_limit": self.request_tokens,
            "context_tokens": self.context_tokens,
            "budget_basis": ("configured_router_cap" if self.context_tokens else "router_application_policy")
            if self.name == "openrouter" and self.model in {"openrouter/free", "openrouter/auto"}
            else ("configured_model_context" if self.context_tokens else "application_policy"),
        }

    def output_limit(self, role):
        return min(
            self.max_output_tokens,
            {
                "semantic_verification": 2048 if self.name == "openrouter" else 1024,
                "context_indexing": 2048,
                "translation_verification": 1024,
                "multilingual_retrieval": 512,
                "question_answering": 2048,
            }.get(role, 4096),
        )

    def fits(self, system: str, prompt: str, schema: dict, role=None) -> bool:
        try:
            _, _, payload = self.request(system, prompt, schema)
        except ProviderError:
            return False
        if role:
            if self.name == "gemini":
                payload["generationConfig"]["maxOutputTokens"] = self.output_limit(role)
            else:
                payload["max_tokens"] = self.output_limit(role)
        if self.name == "openrouter" and role in LOW_REASONING_ROLES:
            payload["reasoning"] = {"effort": "low", "exclude": True}
        usage = self.request_usage(payload)
        return (
            usage["estimated_request_tokens"] <= self.request_tokens
            and usage["payload_bytes"] <= self.max_payload_bytes
        )

    def count_tokens(self, text: str) -> int:
        """Shared tokenizer estimate; authoritative usage comes from provider responses."""
        from app.services.chunking import count_tokens

        return count_tokens(text)

    def health(self) -> dict:
        """Inspect current model availability without sending any source content."""
        if not self.key or not self.model:
            return {"available": False, "code": "PROVIDER_NOT_CONFIGURED"}
        endpoints = {
            "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
            "groq": "https://api.groq.com/openai/v1/models",
            "openrouter": "https://openrouter.ai/api/v1/models",
        }
        headers = (
            {"x-goog-api-key": self.key} if self.name == "gemini" else {"Authorization": f"Bearer {self.key}"}
        )
        try:
            with httpx.Client(
                timeout=min(self.timeout, 10), follow_redirects=False, trust_env=False
            ) as client:
                response = client.get(endpoints[self.name], headers=headers)
            if response.status_code != 200:
                return {"available": False, "code": "PROVIDER_UNAVAILABLE"}
            raw = response.json()
            entries = raw.get("models" if self.name == "gemini" else "data", [])
            entry = next(
                (
                    item
                    for item in entries
                    if item.get("id", item.get("name", "")).removeprefix("models/") == self.model
                ),
                None,
            )
            if entry is None:
                return {
                    "available": False,
                    "code": "MODEL_NOT_LISTED",
                    "complete_catalog": not bool(raw.get("nextPageToken")),
                }
            parameters = entry.get("supported_parameters")
            return {
                "available": True,
                "model": self.model,
                "structured_output_support": (
                    "response_format" in parameters or "structured_outputs" in parameters
                )
                if parameters is not None
                else None,
            }
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return {"available": False, "code": "PROVIDER_UNAVAILABLE"}

    def generate(
        self, system: str, prompt: str, schema_type: type[BaseModel], role: str
    ) -> tuple[BaseModel, list[dict]]:
        calls: list[dict] = []
        corrective = False
        compact = False
        schema_compat = False
        disable_reasoning = False
        if not self.key or not self.model:
            raise ProviderError("PROVIDER_NOT_CONFIGURED")
        if len(system) + len(prompt) > 180000:
            raise ProviderError("PROVIDER_INPUT_BUDGET_EXCEEDED")
        output_budget = self.output_limit(role)
        for attempt in range(min(max(self.retries, 0), 2) + 1):
            started = time.monotonic()
            call = {
                "provider": self.name,
                "model": self.model,
                "role": role,
                "operation": self.operation,
                "attempt": attempt + 1,
                "prompt_version": "evidence-v2.3.0",
                "token_in": None,
                "token_out": None,
                "estimated_cost": None,
            }
            ticket = None
            retryable = False
            retry_after = 0.0
            try:
                if self.budget is not None and time.monotonic() >= self.budget.get("deadline", float("inf")):
                    raise ProviderError("ANALYSIS_DEADLINE_EXCEEDED")
                instruction = ""
                if corrective:
                    instruction += "\nReturn exactly one complete JSON object matching the supplied schema. No markdown, prose, extra fields or invented values."
                if compact and role == "candidate_generation":
                    instruction += "\nReturn at most one atomic finding with a concise rationale and the shortest exact quote that preserves all material conditions. If no complete finding fits, return an empty findings array."
                url, headers, payload = self.request(
                    system, prompt + instruction, schema_type.model_json_schema()
                )
                if schema_compat and self.name != "gemini":
                    payload["response_format"]["json_schema"]["schema"] = strict_wire_schema(
                        schema_type.model_json_schema()
                    )
                if (
                    (compact or role in LOW_REASONING_ROLES)
                    and self.name == "openrouter"
                    and not disable_reasoning
                ):
                    payload["reasoning"] = {"effort": "low", "exclude": True}
                if disable_reasoning:
                    payload.pop("reasoning", None)
                    payload.pop("reasoning_effort", None)
                if compact:
                    call["generation_strategy"] = "bounded_compact_response"
                if schema_compat:
                    call["schema_strategy"] = "compatible_strict_schema"
                if self.on_attempt is not None:
                    self.on_attempt(
                        {"provider": self.name, "model": self.model, "role": role, "attempt": attempt + 1}
                    )
                if self.authorize is not None and not self.authorize():
                    raise ProviderError("PROVIDER_PERMISSION_REVOKED")
                if self.name == "gemini":
                    payload["generationConfig"]["maxOutputTokens"] = output_budget
                else:
                    payload["max_tokens"] = output_budget
                call.update(self.request_usage(payload), budget_phase="local_preflight")
                estimated = call["estimated_request_tokens"]
                if estimated > self.request_tokens or call["payload_bytes"] > self.max_payload_bytes:
                    raise ProviderError("PROVIDER_CONTEXT_LIMIT")

                def check_quota(call=call):
                    wait = self.quota_check() if self.quota_check else 0
                    if wait:
                        call.update(shared_cooldown=True, retry_after_seconds=wait)
                        raise ProviderError("PROVIDER_RATE_LIMITED")

                if self.checkpoint is None:
                    check_quota()
                if self.checkpoint is not None:
                    ticket, cached = self.checkpoint.begin(
                        payload,
                        schema_type.model_json_schema(),
                        role,
                        dict(call),
                        estimated,
                        self.budget,
                        **({"before_reserve": check_quota} if self.quota_check else {}),
                    )
                    if cached:
                        return schema_type.model_validate(cached["value"]), [
                            {
                                **cached["metadata"],
                                "cached": True,
                                "token_in": 0,
                                "token_out": 0,
                                "estimated_cost": 0,
                                "latency_ms": 0,
                                "outcome": "SUCCESS",
                            }
                        ]
                if self.budget is not None:
                    if (
                        self.budget["calls"] >= self.budget["max_calls"]
                        or self.budget["tokens"] + estimated > self.budget["max_tokens"]
                    ):
                        raise ProviderError("PROVIDER_OPERATION_BUDGET_EXCEEDED")
                    self.budget["calls"] += 1
                    self.budget["tokens"] += estimated
                # Fixed provider URLs only. Ignore ambient proxies and never follow redirects.
                with httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=False) as client:
                    call["request_sent"] = True
                    response = client.post(url, headers=headers, json=payload)
                call["http_status"] = response.status_code
                call["budget_phase"] = "provider_response"
                if response.status_code != 200:
                    header = response.headers.get("Retry-After", "")
                    try:
                        retry_after = max(0.0, float(header))
                    except ValueError:
                        try:
                            retry_after = max(
                                0.0,
                                (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds(),
                            )
                        except (ValueError, TypeError, OverflowError):
                            retry_after = 0.0
                    # Never retry earlier than requested; long waits require an explicit later retry.
                    retry_after = max(retry_after, structured_retry_delay(response))
                    quota_wait = retry_after
                    if not 0 <= retry_after <= 30:
                        retry_after = 31.0
                    retryable = response.status_code in {408, 429, 500, 502, 503, 504}
                    call["retry_after_over_budget"] = retry_after > 30
                    code = {
                        400: "PROVIDER_REQUEST_REJECTED",
                        401: "PROVIDER_AUTH_FAILED",
                        403: "PROVIDER_AUTH_FAILED",
                        404: "PROVIDER_MODEL_UNAVAILABLE",
                        413: "PROVIDER_CONTEXT_LIMIT",
                        422: "PROVIDER_REQUEST_REJECTED",
                        429: "PROVIDER_RATE_LIMITED",
                    }.get(response.status_code, "PROVIDER_UNAVAILABLE")
                    if response.status_code == 400:
                        try:
                            error = response.json().get("error", {})
                            message = error.get("message", "")
                            if error.get("code") == "context_length_exceeded" or (
                                isinstance(message, str)
                                and re.search(
                                    r"maximum context length|context window exceeded|context_length_exceeded",
                                    message,
                                    re.IGNORECASE,
                                )
                            ):
                                code = "PROVIDER_CONTEXT_LIMIT"
                        except (ValueError, AttributeError, TypeError):
                            pass
                    if response.status_code == 429:
                        retryable = False
                        call["retry_after_seconds"] = quota_wait or 60
                        if self.quota_block:
                            self.quota_block(call["retry_after_seconds"])
                    call.update(error_details(response))
                    if response.status_code == 400:
                        if call.get("validation_issue") == "CONTEXT_LENGTH":
                            code = "PROVIDER_CONTEXT_LIMIT"
                        if (
                            (
                                call.get("validation_issue")
                                in {"SCHEMA_UNSUPPORTED", "SCHEMA_CLOSED_OBJECT", "SCHEMA_REQUIRED_FIELDS"}
                                or call.get("provider_error_code") == "invalid_json_schema"
                            )
                            and not schema_compat
                            and self.name != "gemini"
                            and strict_wire_schema(schema_type.model_json_schema())
                            != payload["response_format"]["json_schema"]["schema"]
                        ):
                            schema_compat = True
                            retryable = True
                        elif (
                            call.get("validation_issue") == "REASONING_UNSUPPORTED"
                            or call.get("provider_error_param")
                            in {"reasoning", "reasoning_effort", "reasoning.effort", "reasoning.exclude"}
                        ) and not disable_reasoning:
                            disable_reasoning = True
                            retryable = True
                    if response.status_code == 400 and (
                        call.get("provider_error_code") == "json_validate_failed"
                        or call.get("validation_issue") == "GENERATED_SCHEMA_MISMATCH"
                    ):
                        code = "PROVIDER_INVALID_OUTPUT"
                        retryable = not corrective
                        corrective = True
                    raise ProviderError(code)
                raw = response.json()
                if not isinstance(raw, dict):
                    raise TypeError("Invalid response object")
                response_model = raw.get("model", raw.get("modelVersion"))
                safe_model = (
                    response_model
                    if isinstance(response_model, str)
                    and re.fullmatch(
                        r"(?:gemini-[A-Za-z0-9._:-]+|[A-Za-z0-9._-]+/[A-Za-z0-9/._:-]+)", response_model
                    )
                    and len(response_model) <= 160
                    else None
                )
                call.update(requested_model=self.model, response_model=safe_model)
                usage = raw.get("usageMetadata" if self.name == "gemini" else "usage", {})
                for target, value in {
                    "token_in": usage.get("promptTokenCount", usage.get("prompt_tokens")),
                    "token_out": usage.get("candidatesTokenCount", usage.get("completion_tokens")),
                    "reasoning_tokens": usage.get(
                        "thoughtsTokenCount",
                        usage.get("completion_tokens_details", {}).get("reasoning_tokens"),
                    ),
                }.items():
                    if type(value) is int and 0 <= value <= 1000000000:
                        call[target] = value
                if self.name == "gemini":
                    candidates = raw.get("candidates") or []
                    reason = candidates[0].get("finishReason", "UNKNOWN") if candidates else "UNKNOWN"
                    allowed = {
                        "STOP",
                        "MAX_TOKENS",
                        "SAFETY",
                        "RECITATION",
                        "LANGUAGE",
                        "OTHER",
                        "BLOCKLIST",
                        "PROHIBITED_CONTENT",
                        "SPII",
                        "MALFORMED_FUNCTION_CALL",
                        "UNEXPECTED_TOOL_CALL",
                        "NO_IMAGE",
                    }
                    call["finish_reason"] = reason if reason in allowed else "UNKNOWN"
                    if raw.get("promptFeedback", {}).get("blockReason") or reason in {
                        "SAFETY",
                        "RECITATION",
                        "BLOCKLIST",
                        "PROHIBITED_CONTENT",
                        "SPII",
                    }:
                        raise ProviderError("PROVIDER_CONTENT_BLOCKED")
                    if reason == "MAX_TOKENS":
                        retryable = output_budget < self.max_output_tokens or (
                            role == "candidate_generation" and not compact
                        )
                        if output_budget >= self.max_output_tokens and role == "candidate_generation":
                            compact = True
                        next_budget = min(output_budget * 2, 8192, self.max_output_tokens)
                        if call["estimated_input_tokens"] + next_budget <= self.request_tokens:
                            output_budget = next_budget
                        else:
                            retryable = role == "candidate_generation" and not compact
                            compact = True
                        raise ProviderError("PROVIDER_OUTPUT_LIMIT")
                if (
                    self.name != "gemini"
                    and raw.get("choices")
                    and raw["choices"][0].get("finish_reason") == "length"
                ):
                    call["finish_reason"] = "length"
                    retryable = output_budget < self.max_output_tokens or (
                        role == "candidate_generation" and not compact
                    )
                    if output_budget >= self.max_output_tokens and role == "candidate_generation":
                        compact = True
                    next_budget = min(output_budget * 2, 8192, self.max_output_tokens)
                    if call["estimated_input_tokens"] + next_budget <= self.request_tokens:
                        output_budget = next_budget
                    else:
                        retryable = role == "candidate_generation" and not compact
                        compact = True
                    raise ProviderError("PROVIDER_OUTPUT_LIMIT")
                content, token_in, token_out = self.unpack(raw)
                call.update(token_in=token_in, token_out=token_out)
                if (
                    token_in is not None
                    and token_out is not None
                    and self.input_price_per_million is not None
                    and self.output_price_per_million is not None
                ):
                    call["estimated_cost"] = (
                        token_in * self.input_price_per_million + token_out * self.output_price_per_million
                    ) / 1_000_000
                value = schema_type.model_validate_json(json_content(content))
                call["outcome"] = "SUCCESS"
                call["latency_ms"] = round((time.monotonic() - started) * 1000)
                if ticket is not None:
                    self.checkpoint.finish(ticket, value.model_dump(), dict(call))
                calls.append(call)
                return value, calls
            except httpx.TimeoutException:
                code, retryable = "PROVIDER_TIMEOUT", True
            except httpx.HTTPError:
                code, retryable = "PROVIDER_UNAVAILABLE", True
            except (ValidationError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
                call.update(validation_details(exc))
                code, retryable = "PROVIDER_INVALID_OUTPUT", not corrective
                corrective = True
            except ProviderError as exc:
                code = exc.code
            if ticket is not None:
                self.checkpoint.fail(ticket, code)
            call.update(outcome=code, latency_ms=round((time.monotonic() - started) * 1000))
            calls.append(call)
            # Strict whitelist: no raw response, request, exception text, credentials or source text.
            diagnostic = {
                k: call[k]
                for k in (
                    "provider",
                    "model",
                    "response_model",
                    "role",
                    "operation",
                    "attempt",
                    "http_status",
                    "finish_reason",
                    "outcome",
                    "latency_ms",
                    "estimated_input_tokens",
                    "reserved_output_tokens",
                    "estimated_request_tokens",
                    "request_token_limit",
                    "payload_bytes",
                    "budget_phase",
                    "budget_basis",
                    "provider_error_code",
                    "provider_error_type",
                    "provider_error_param",
                    "validation_issue",
                    "validation_types",
                    "reasoning_tokens",
                    "generation_strategy",
                    "schema_strategy",
                    "shared_cooldown",
                    "retry_after_seconds",
                )
                if k in call
            }
            diagnostic["model"] = re.sub(r"[^A-Za-z0-9/._:-]", "", self.model)[:120]
            logging.getLogger("veriora.provider").warning("provider_failure %s", json.dumps(diagnostic))
            if retry_after > 30:
                raise ProviderError(code, calls=calls) from None
            if not retryable or attempt >= min(max(self.retries, 0), 2):
                raise ProviderError(code, calls=calls) from None
            time.sleep(max(retry_after, min(2 ** (attempt + 1), 8) + random.uniform(0, 1)))
        raise ProviderError("PROVIDER_UNAVAILABLE", calls=calls)

    def unpack(self, raw: dict) -> tuple[str, int | None, int | None]:
        choice = raw["choices"][0]
        if choice["message"].get("refusal") or choice.get("finish_reason") == "content_filter":
            raise ProviderError("PROVIDER_CONTENT_BLOCKED")
        if choice.get("finish_reason") != "stop":
            raise ProviderError("PROVIDER_INCOMPLETE_OUTPUT")
        usage = raw.get("usage", {})
        content = choice["message"]["content"]
        if isinstance(content, list) and all(
            isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str)
            for p in content
        ):
            content = "".join(p["text"] for p in content)
        return content, usage.get("prompt_tokens"), usage.get("completion_tokens")


class CompatibleProvider(ModelProvider):
    def request(self, system: str, prompt: str, schema: dict) -> tuple[str, dict, dict]:
        endpoints = {
            "groq": "https://api.groq.com/openai/v1/chat/completions",
            "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": min(4096, self.max_output_tokens),
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "veriora_output", "strict": True, "schema": schema},
            },
        }
        if self.name == "groq" and self.model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
            payload["reasoning_effort"] = "low"
        if self.name == "openrouter":
            # Prevent OpenRouter's internal model fallback and require schema capability.
            payload["provider"] = {"require_parameters": True, "allow_fallbacks": False}
        return endpoints[self.name], {"Authorization": f"Bearer {self.key}"}, payload


class GeminiProvider(ModelProvider):
    def request(self, system: str, prompt: str, schema: dict) -> tuple[str, dict, dict]:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", self.model):
            raise ProviderError("PROVIDER_INVALID_MODEL")
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            {"x-goog-api-key": self.key},
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0,
                    "maxOutputTokens": min(4096, self.max_output_tokens),
                    "responseMimeType": "application/json",
                    "responseJsonSchema": gemini_schema(schema),
                },
            },
        )

    def unpack(self, raw: dict) -> tuple[str, int | None, int | None]:
        candidate = raw["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ProviderError("PROVIDER_INCOMPLETE_OUTPUT")
        content = "".join(
            part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought")
        )
        usage = raw.get("usageMetadata", {})
        return content, usage.get("promptTokenCount"), usage.get("candidatesTokenCount")


def configured_provider(config: dict) -> ModelProvider:
    name = config.get("name", "")
    if name not in {"gemini", "groq", "openrouter"}:
        raise ProviderError("PROVIDER_NOT_SUPPORTED")
    cls = GeminiProvider if name == "gemini" else CompatibleProvider
    return cls(
        name=name,
        model=config.get("model", ""),
        key=config.get("key", ""),
        on_attempt=config.get("on_attempt"),
        authorize=config.get("authorize"),
        budget=config.get("budget"),
        checkpoint=config.get("checkpoint"),
        operation=config.get("operation", "analysis"),
        quota_check=config.get("quota_check"),
        quota_block=config.get("quota_block"),
        context_tokens=int(config["context_tokens"]) if config.get("context_tokens") is not None else None,
        request_tokens=max(
            1,
            min(
                int(config.get("request_tokens", {"groq": 6000, "gemini": 24000, "openrouter": 12000}[name])),
                int(
                    config.get(
                        "context_tokens",
                        config.get(
                            "request_tokens", {"groq": 6000, "gemini": 24000, "openrouter": 12000}[name]
                        ),
                    )
                ),
            ),
        ),
        max_output_tokens=max(
            1,
            min(
                int(
                    config.get("max_output_tokens", {"groq": 2048, "gemini": 8192, "openrouter": 4096}[name])
                ),
                8192,
            ),
        ),
        max_payload_bytes=max(1, min(int(config.get("max_payload_bytes", 256000)), 1000000)),
        timeout=min(float(config.get("timeout", 40)), 60),
        retries=int(config.get("retries", 2)),
        input_price_per_million=config.get("input_price_per_million"),
        output_price_per_million=config.get("output_price_per_million"),
    )


def budget_available_configs(configs):
    """Use only currently eligible models when sizing a payload, without sending data."""
    eligible, blocked = [], []
    for config in configs:
        if config.get("name") not in {"gemini", "groq", "openrouter"}:
            eligible.append(config)
            continue
        budget = config.get("budget") or {}
        code = (
            budget.get("unavailable_codes", {}).get(config["name"])
            if config["name"] in budget.get("unavailable", set())
            else None
        )
        wait = config["quota_check"]() if not code and config.get("quota_check") else 0
        if wait:
            code = "PROVIDER_RATE_LIMITED"
        if code:
            blocked.append(
                {
                    "provider": config["name"],
                    "model": config.get("model"),
                    "operation": config.get("operation", "analysis"),
                    "role": "provider_selection",
                    "outcome": code,
                    "attempt": 0,
                    "retry_after_seconds": wait,
                    "request_sent": False,
                }
            )
            if config.get("budget") is not None:
                config["budget"].setdefault("unavailable", set()).add(config["name"])
                config["budget"].setdefault("unavailable_codes", {})[config["name"]] = code
        else:
            eligible.append(config)
    if not eligible and blocked:
        raise ProviderError(
            next(
                (c["outcome"] for c in blocked if c["outcome"] == "PROVIDER_RATE_LIMITED"),
                blocked[-1]["outcome"],
            ),
            calls=blocked,
        )
    return eligible


def generate_with_fallback(
    configs: list[dict], system: str, prompt: str, schema_type: type[BaseModel], role: str
) -> tuple[BaseModel, list[dict]]:
    """Only the caller's explicit consent-filtered list may receive document text."""
    if not configs:
        raise ProviderError("PROVIDER_NOT_CONFIGURED")
    calls: list[dict] = []
    last_code = "PROVIDER_NOT_CONFIGURED"
    for index, config in enumerate(list({c.get("name"): c for c in reversed(configs[:3])}.values())[::-1]):
        budget = config.get("budget")
        if budget is not None and (config.get("name"), role) in budget.get(
            "exhausted_reasoning_tasks", set()
        ):
            last_code = "PROVIDER_OUTPUT_LIMIT"
            calls.append(
                {
                    "provider": config["name"],
                    "model": config.get("model"),
                    "role": role,
                    "operation": config.get("operation", "analysis"),
                    "outcome": last_code,
                    "attempt": 0,
                    "cached_rejection": True,
                    "generation_strategy": "reasoning_exhaustion_circuit",
                }
            )
            continue
        if budget is not None and (config.get("name"), role) in budget.get("rejected_tasks", set()):
            last_code = "PROVIDER_REQUEST_REJECTED"
            calls.append(
                {
                    "provider": config["name"],
                    "model": config.get("model"),
                    "role": role,
                    "operation": config.get("operation", "analysis"),
                    "outcome": last_code,
                    "attempt": 0,
                    "cached_rejection": True,
                }
            )
            continue
        if budget is not None and config.get("name") in budget.get("unavailable", set()):
            last_code = budget.get("unavailable_codes", {}).get(config.get("name"), "PROVIDER_UNAVAILABLE")
            calls.append(
                {
                    "provider": config["name"],
                    "model": config.get("model"),
                    "role": role,
                    "operation": config.get("operation", "analysis"),
                    "attempt": 0,
                    "outcome": last_code,
                    "skipped_unavailable": True,
                    "fallback": index > 0,
                }
            )
            continue
        try:
            value, new_calls = configured_provider(config).generate(system, prompt, schema_type, role)
            for call in new_calls:
                call["fallback"] = index > 0
            calls.extend(new_calls)
            return value, calls
        except ProviderError as exc:
            last_code = exc.code
            if (
                budget is not None
                and role in LOW_REASONING_ROLES
                and last_code == "PROVIDER_OUTPUT_LIMIT"
                and sum(
                    c.get("reasoning_tokens", 0) >= c.get("reserved_output_tokens", 1) > 0
                    and c.get("finish_reason") in {"length", "MAX_TOKENS"}
                    for c in exc.model_calls
                )
                >= 2
            ):
                budget.setdefault("exhausted_reasoning_tasks", set()).add((config.get("name"), role))
            if budget is not None and last_code == "PROVIDER_REQUEST_REJECTED":
                budget.setdefault("rejected_tasks", set()).add((config.get("name"), role))
            if budget is not None and last_code in {
                "PROVIDER_UNAVAILABLE",
                "PROVIDER_RATE_LIMITED",
                "PROVIDER_TIMEOUT",
                "PROVIDER_AUTH_FAILED",
                "PROVIDER_MODEL_UNAVAILABLE",
            }:
                budget.setdefault("unavailable", set()).add(config.get("name"))
                budget.setdefault("unavailable_codes", {})[config.get("name")] = last_code
            for call in exc.model_calls:
                call["fallback"] = index > 0
            calls.extend(exc.model_calls)
            logging.getLogger("veriora.provider").info(
                "provider_transition role=%s failed_provider=%s code=%s remaining_authorized=%s",
                role,
                config.get("name"),
                last_code,
                max(0, len(configs[:3]) - index - 1),
            )
            if last_code in {
                "PROVIDER_CONTENT_BLOCKED",
                "PROVIDER_OPERATION_BUDGET_EXCEEDED",
                "PROVIDER_CHECKPOINT_UNCERTAIN",
                "PROVIDER_JOB_INTERRUPTED",
                "ANALYSIS_DEADLINE_EXCEEDED",
            }:
                break
    raise ProviderError(last_code, calls=calls)


def input_budget(config: dict, schema_type: type[BaseModel]) -> int:
    """Conservative text allowance after complete wire-schema/output overhead."""
    provider = configured_provider(config)
    try:
        _, _, payload = provider.request("", "", schema_type.model_json_schema())
    except ProviderError:
        return 0
    output = payload.get("max_tokens", payload.get("generationConfig", {}).get("maxOutputTokens", 4096))
    overhead = provider.count_tokens(json.dumps(payload, ensure_ascii=False))
    return max(0, int((provider.request_tokens - output - 512) / 1.2) - overhead)
