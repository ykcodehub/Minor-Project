/** Static guidance only; never interprets provider output as document evidence. */
export function providerFailure(error: string): string | undefined {
  if (error.includes("PROVIDER_VERDICT_UNGROUNDED"))
    return "The reviewer cited source references that are not written in the supplied text. The interpretation remains unverified; use another authorized reviewer.";
  if (error.includes("PROVIDER_CATEGORY_MISMATCH"))
    return "The reviewer rejected the proposed finding category. The finding remains unverified rather than receiving a misleading risk label.";
  if (error.includes("PROVIDER_NO_HEALTHY_ENDPOINT"))
    return "No healthy compatible endpoint is available for this model. Retry later or open the labeled offline synthetic demo; no model was substituted.";
  if (error.includes("PROVIDER_EXPLICIT_MODEL_REQUIRED"))
    return "The configured dynamic router is unsuitable for verified analysis. Ask the administrator to configure an explicit model; provider permissions have not changed.";
  if (error.includes("PROVIDER_REASONING_EXHAUSTED"))
    return "The model spent its output allowance on reasoning. Repeated document splitting will not fix this. Choose a compatible authorized model; results remain unverified.";
  if (
    error.includes("PROVIDER_REASONING_INCOMPATIBLE") ||
    error.includes("PROVIDER_MODEL_INCOMPATIBLE")
  )
    return "The configured model cannot safely produce bounded structured results. Ask the administrator to select a compatible explicit model.";
  if (error.includes("PROVIDER_CAPABILITIES_UNAVAILABLE"))
    return "Model capabilities could not be checked. No document was sent to that model; retry when its catalog is available.";
  if (error.includes("PROVIDER_TEMPORARILY_SUPPRESSED"))
    return "The provider is temporarily paused after an outage. Retry later or use an already authorized alternative.";
  if (error.includes("ANALYSIS_DEADLINE_EXCEEDED"))
    return "Processing reached its time limit. Inspect preserved results and checkpointed usage before retrying.";
  if (error.includes("PROVIDER_CHECKPOINT_UNCERTAIN"))
    return "An interrupted AI request has no saved response. Review possible usage before explicitly retrying it; completed responses will be reused.";
  if (error.includes("PROVIDER_CONTEXT_INCOMPLETE"))
    return "The source-wide qualification audit is incomplete. Results remain unverified; inspect coverage before retrying.";
  if (error.includes("PROVIDER_PERMISSION_REVOKED"))
    return "AI permission was revoked. Review authorized providers in Settings before retrying.";
  if (error.includes("PROVIDER_OPERATION_BUDGET_EXCEEDED"))
    return "The operation reached its bounded AI budget. Review partial findings before starting another analysis.";
  if (error.includes("PROVIDER_CONTEXT_LIMIT"))
    return "The request exceeds an application or provider context budget. Review coverage and use a smaller source or an authorized alternative.";
  if (error.includes("PROVIDER_CONTENT_BLOCKED"))
    return "The provider blocked generation. Repeated retries are unlikely to help. Inspect the source; no verified result was produced.";
  if (error.includes("PROVIDER_OUTPUT_LIMIT"))
    return "The provider exhausted its output allowance. Review partial evidence and choose a compatible, authorized provider in Settings before retrying; truncated output was rejected.";
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
