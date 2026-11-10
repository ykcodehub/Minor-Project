/** Static guidance only; never interprets provider output as document evidence. */
export function providerFailure(error: string): string | undefined {
  if (error.includes("PROVIDER_PERMISSION_REVOKED"))
    return "AI permission was revoked. Review authorized providers in Settings before retrying.";
  if (error.includes("PROVIDER_OPERATION_BUDGET_EXCEEDED"))
    return "The operation reached its bounded AI budget. Review partial findings before starting another analysis.";
  if (error.includes("PROVIDER_CONTEXT_LIMIT"))
    return "The provider rejected the request size or token budget. Authorized alternatives were considered; inspect coverage and try a smaller source.";
  if (error.includes("PROVIDER_CONTENT_BLOCKED"))
    return "The provider blocked generation. Repeated retries are unlikely to help. Inspect the source; no verified result was produced.";
  if (error.includes("PROVIDER_OUTPUT_LIMIT"))
    return "The provider reached its output limit after bounded recovery. Try analyzing a smaller document; incomplete output was not accepted.";
  if (
    error.includes("PROVIDER_AUTH_FAILED") ||
    error.includes("PROVIDER_MODEL_UNAVAILABLE") ||
    error.includes("PROVIDER_REQUEST_REJECTED")
  )
    return "The selected provider needs a configuration check. Ask the administrator to verify credentials, model access and structured-output support before retrying.";
  if (error.includes("PROVIDER_RATE_LIMITED"))
    return "The selected provider is rate-limited. Wait for quota to recover before retrying.";
  if (
    error.includes("PROVIDER_UNAVAILABLE") ||
    error.includes("PROVIDER_TIMEOUT")
  )
    return "The selected provider is temporarily unavailable. Retry later using the same authorized provider. Automatic retries are limited.";
  if (
    error.includes("PROVIDER_INVALID_OUTPUT") ||
    error.includes("PROVIDER_INCOMPLETE_OUTPUT")
  )
    return "The provider did not return valid, complete structured output. No verified result was produced. You may retry later.";
  return undefined;
}
