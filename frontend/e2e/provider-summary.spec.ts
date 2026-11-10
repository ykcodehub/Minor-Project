import { test, expect } from "@playwright/test";
// Synthetic API fixtures exercise browser integration without accounts or paid AI.
test("saved permissions persist in settings and remove repeated source consent", async ({
  page,
}) => {
  let allowed = ["gemini"];
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/me") {
      if (route.request().method() === "PATCH")
        allowed = route.request().postDataJSON().authorized_providers;
      return route.fulfill({
        json: {
          id: "synthetic",
          email: "synthetic@example.com",
          is_guest: false,
          verified: true,
          language: "en",
          retention_days: 30,
          csrf_token: "fixture",
          preferred_provider: "gemini",
          authorized_providers: allowed,
          providers: [
            { name: "gemini", model: "fixture", configured: true },
            { name: "groq", model: "fixture", configured: true },
          ],
        },
      });
    }
    if (path === "/api/v1/sources/synthetic")
      return route.fulfill({
        json: {
          id: "synthetic",
          original_name: "synthetic.txt",
          status: "READY",
          kind: "text",
          sha256: "a".repeat(64),
          captured_at: new Date().toISOString(),
          sections: [
            {
              id: "sec",
              source_id: "synthetic",
              ordinal: 0,
              text: "Synthetic term.",
            },
          ],
        },
      });
    return route.fulfill({ json: [] });
  });
  await page.goto("/settings");
  await page.getByRole("checkbox", { name: /groq/ }).check();
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect.poll(() => allowed).toEqual(["gemini", "groq"]);
  await page.goto("/source/synthetic");
  await expect(
    page.getByText("Saved provider permissions apply automatically.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Analyze document" }),
  ).toBeEnabled();
});

test("partial summary shows verified counts and failure reason", async ({
  page,
}) => {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];
    if (path === "/api/v1/me")
      data = {
        id: "synthetic",
        email: "synthetic@example.com",
        is_guest: false,
        verified: true,
        language: "en",
        retention_days: 30,
        csrf_token: "fixture",
        providers: [],
      };
    else if (path === "/api/v1/analyses/synthetic")
      data = {
        id: "synthetic",
        job_id: "job",
        status: "PARTIAL_COMPLETION",
        sources: [],
        source_ids: [],
        coverage: {},
        limitations: [],
        findings_count: 20,
      };
    else if (path === "/api/v1/jobs/job")
      data = {
        job_id: "job",
        state: "PARTIAL_COMPLETION",
        stage: "COMPLETED",
        result: {},
        progress: {},
      };
    else if (path === "/api/v1/analyses/synthetic/summary")
      data = {
        summary: {
          level: "Not Determinable",
          rule: "Incomplete verification",
          rule_version: "test",
          disclaimer: "Not legal advice",
          groups: {},
          counts: { retained: 20, verified: 0, excluded: 20 },
          processing_state: "PARTIAL_COMPLETION",
          failure_codes: ["PROVIDER_CONTEXT_LIMIT"],
        },
        translations: {},
        translation_ready: true,
      };
    return route.fulfill({ json: data });
  });
  await page.goto("/analysis/synthetic");
  await expect(page.getByText(/20 findings require review/)).toBeVisible();
  await expect(page.getByText(/No interpretation has passed/)).toBeVisible();
  await page.getByText("Processing failure reasons", { exact: true }).click();
  await expect(page.getByText(/^PROVIDER_CONTEXT_LIMIT:/)).toBeVisible();
});
