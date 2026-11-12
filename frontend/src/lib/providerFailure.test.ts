import { describe, expect, it } from "vitest";
import { providerFailure } from "./providerFailure";
describe("provider failure guidance", () => {
  it.each([
    "CHECKPOINT_UNCERTAIN",
    "CONTEXT_INCOMPLETE",
    "CONTEXT_LIMIT",
    "PERMISSION_REVOKED",
    "OPERATION_BUDGET_EXCEEDED",
    "UNAVAILABLE",
    "TIMEOUT",
    "CONTENT_BLOCKED",
    "OUTPUT_LIMIT",
    "AUTH_FAILED",
    "MODEL_UNAVAILABLE",
    "RATE_LIMITED",
    "INVALID_OUTPUT",
    "INCOMPLETE_OUTPUT",
    "NO_HEALTHY_ENDPOINT",
    "VERDICT_UNGROUNDED",
    "CATEGORY_MISMATCH",
    "EXPLICIT_MODEL_REQUIRED",
    "REASONING_EXHAUSTED",
    "REASONING_INCOMPATIBLE",
    "MODEL_INCOMPATIBLE",
    "CAPABILITIES_UNAVAILABLE",
    "TEMPORARILY_SUPPRESSED",
  ])("explains %s", (code) => {
    expect(
      providerFailure(
        `AI provider failed: ANALYSIS_GENERATION_FAILED. PROVIDER_${code}`,
      ),
    ).toBeTruthy();
  });
  it("explains terminal time limits", () => {
    expect(providerFailure("ANALYSIS_DEADLINE_EXCEEDED")).toContain(
      "checkpointed usage",
    );
  });
  it("does not reinterpret unrelated failures", () =>
    expect(providerFailure("Extraction failed")).toBeUndefined());
});
