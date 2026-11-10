"""Allowlisted provider diagnostics. Never retain provider prose, failed generations or values."""

import re

CODES = {
    "invalid_request_error",
    "invalid_api_key",
    "model_not_found",
    "json_validate_failed",
    "invalid_json_schema",
    "unsupported_parameter",
    "context_length_exceeded",
    "rate_limit_exceeded",
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "INVALID_ARGUMENT",
    "PERMISSION_DENIED",
}
PARAMS = {
    "response_format",
    "response_format.json_schema",
    "response_format.json_schema.schema",
    "temperature",
    "max_tokens",
    "max_completion_tokens",
    "reasoning",
    "reasoning_effort",
}


def error_details(response):
    result = {"validation_issue": "DETAILS_REDACTED"}
    try:
        error = response.json().get("error", {})
        if not isinstance(error, dict):
            return result
        for key in ("code", "type"):
            if isinstance(error.get(key), str) and error[key] in CODES:
                result["provider_error_" + key] = error[key]
        if error.get("param") in PARAMS:
            result["provider_error_param"] = error["param"]
        message = error.get("message", "")
        if not isinstance(message, str):
            return result
        patterns = [
            ("CONTEXT_LENGTH", r"maximum context length|context window exceeded|context_length_exceeded"),
            ("SCHEMA_UNSUPPORTED", r"unsupported.*schema|schema.*not supported|invalid.*json.schema"),
            ("SCHEMA_CLOSED_OBJECT", r"additionalProperties"),
            ("SCHEMA_REQUIRED_FIELDS", r"required.*propert|propert.*required"),
            (
                "REASONING_UNSUPPORTED",
                r"reasoning.*(?:unsupported|not supported)|(?:unsupported|not supported).*reasoning",
            ),
            ("GENERATED_SCHEMA_MISMATCH", r"generated json.*(?:schema|valid)|failed to generate json"),
            ("OUTPUT_BUDGET_INVALID", r"max_(?:completion_)?tokens.*(?:invalid|must|limit)"),
        ]
        for issue, pattern in patterns:
            if re.search(pattern, message, re.IGNORECASE):
                result["validation_issue"] = issue
                break
    except (ValueError, TypeError, AttributeError):
        pass
    return result


def validation_details(exc):
    allowed = {
        "missing",
        "extra_forbidden",
        "json_invalid",
        "string_type",
        "int_type",
        "literal_error",
        "string_too_long",
        "string_too_short",
        "too_long",
        "too_short",
        "list_type",
        "model_type",
        "bool_type",
    }
    if not hasattr(exc, "errors"):
        return {"validation_types": ["invalid_json_or_shape"]}
    return {
        "validation_types": sorted(
            {
                e.get("type") if e.get("type") in allowed else "schema_violation"
                for e in exc.errors(include_input=False, include_url=False)
            }
        )
    }


def strict_wire_schema(schema):
    """Conditional compatibility normalization. Local Pydantic retains removed bounds."""
    if isinstance(schema, list):
        return [strict_wire_schema(v) for v in schema]
    if not isinstance(schema, dict):
        return schema
    result = {
        k: (
            {name: strict_wire_schema(value) for name, value in v.items()}
            if k in {"properties", "$defs", "definitions"} and isinstance(v, dict)
            else strict_wire_schema(v)
        )
        for k, v in schema.items()
        if k
        not in {"title", "default", "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"}
    }
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    return result


def json_content(content):
    if not isinstance(content, str):
        raise TypeError("Non-text JSON content")
    text = content.strip()
    if text.startswith("```json\n") and text.endswith("\n```") and text.count("```") == 2:
        return text[8:-4].strip()
    return text
