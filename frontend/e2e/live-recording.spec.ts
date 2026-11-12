import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Replay the recorded real response, not another inference. Never claim this is a live browser-provider test.
test("recorded Dots partial analysis stays unverified in the real workspace", async ({
  page,
}) => {
  const report = JSON.parse(
    readFileSync(
      resolve("../docs/benchmarks/college_live_compact.json"),
      "utf8",
    ),
  );
  expect(report.model).toBe("dots-studio/dots-3-note-preview:free");
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];
    if (path === "/api/v1/me")
      data = {
        id: "fixture",
        email: "fixture@example.com",
        is_guest: false,
        language: "en",
        csrf_token: "fixture",
        providers: [],
      };
    else if (path === "/api/v1/analyses/recorded")
      data = {
        id: "recorded",
        job_id: "job",
        status: "PARTIAL_COMPLETION",
        sources: [],
        source_ids: [],
        coverage: report.coverage,
        limitations: [],
        findings_count: report.findings.length,
      };
    else if (path === "/api/v1/jobs/job")
      data = {
        id: "job",
        state: "PARTIAL_COMPLETION",
        stage: "PARTIAL_COMPLETION",
        progress: {},
        result: {},
        error: "PROVIDER_REQUEST_REJECTED",
      };
    else if (path.endsWith("/summary"))
      data = {
        summary: report.summary,
        translations: {},
        translation_ready: true,
      };
    await route.fulfill({ json: data });
  });
  await page.goto("/analysis/recorded");
  await expect(
    page.getByText("Not Determinable", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator(".risk-segments")).toHaveAttribute(
    "aria-label",
    "Low: 0, Moderate: 0, High: 0",
  );
  await expect(page.getByText(/6 findings require review/)).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open offline synthetic demo" }),
  ).toBeVisible();
});
