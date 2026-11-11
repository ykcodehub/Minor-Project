import { test, expect } from "@playwright/test";
for (const mobile of [false, true])
  test(`Ask Veriora quota error ${mobile ? "mobile" : "desktop"} is not an unsupported answer`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: mobile ? 390 : 1280, height: 900 });
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = [];
      if (path === "/api/v1/me")
        data = {
          id: "fixture",
          email: "fixture@example.com",
          guest: false,
          is_guest: false,
          language: "en",
          csrf_token: "fixture",
          providers: [],
        };
      else if (path === "/api/v1/analyses/ops")
        data = {
          analysis_id: "ops",
          status: "PARTIAL_COMPLETION",
          job_id: "job",
          source_ids: [],
          sources: [],
          coverage: {},
          findings_count: 0,
          limitations: [],
        };
      else if (path === "/api/v1/jobs/job")
        data = {
          id: "job",
          state: "PARTIAL_COMPLETION",
          stage: "PARTIAL_COMPLETION",
          progress: {},
          result: {},
        };
      else if (path.endsWith("/summary"))
        data = {
          summary: {
            level: "Not Determinable",
            rule: "Incomplete verification.",
            rule_version: "fixture",
            disclaimer: "Synthetic test",
            groups: {},
            counts: { retained: 0, verified: 0, excluded: 0 },
          },
          translation_ready: true,
          translations: {},
        };
      else if (
        path.endsWith("/questions") &&
        route.request().method() === "POST"
      ) {
        await route.fulfill({
          status: 503,
          headers: { "Retry-After": "90" },
          json: {
            code: "PROVIDER_RATE_LIMITED",
            message:
              "Ask Veriora unavailable: PROVIDER_RATE_LIMITED. No answer has been verified.",
          },
        });
        return;
      }
      await route.fulfill({ json: data });
    });
    await page.goto("/analysis/ops");
    await page
      .getByRole("tab", { name: "Detailed Analysis", exact: true })
      .click();
    await page.getByRole("tab", { name: "Ask Veriora", exact: true }).click();
    await page
      .getByLabel("Your document question")
      .fill("When is payment due?");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(
      page.getByRole("alert").filter({ hasText: "PROVIDER_RATE_LIMITED" }),
    ).toBeVisible();
    await expect(page.getByText(/Provider retry delay.*90/)).toBeVisible();
    await expect(page.locator(".citation-chip")).toHaveCount(0);
    await expect(page.locator(".answer")).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
  });
test("partial translation cache remains honest and does not automatically retry an unavailable provider", async ({
  page,
}) => {
  let translations = 0;
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = [];
    if (path === "/api/v1/me")
      data = {
        id: "fixture",
        email: "fixture@example.com",
        guest: false,
        is_guest: false,
        language: "hinglish",
        csrf_token: "fixture",
        providers: [],
      };
    else if (path === "/api/v1/analyses/ops")
      data = {
        analysis_id: "ops",
        status: "PARTIAL_COMPLETION",
        job_id: "job",
        source_ids: [],
        sources: [],
        coverage: {},
        findings_count: 7,
        limitations: [],
      };
    else if (path === "/api/v1/jobs/job")
      data = {
        id: "job",
        state: "PARTIAL_COMPLETION",
        stage: "PARTIAL_COMPLETION",
        progress: {},
        result: {},
      };
    else if (path.endsWith("/summary"))
      data = {
        summary: {
          level: "Not Determinable",
          rule: "Incomplete verification.",
          rule_version: "fixture",
          disclaimer: "Synthetic test",
          groups: {},
          counts: { retained: 7, verified: 0, excluded: 7 },
        },
        translation_ready: false,
        translation_completed: 4,
        translation_total: 7,
        translations: {},
        fingerprint: "same-fixture",
      };
    else if (path.endsWith("/translations")) {
      translations++;
      await route.fulfill({
        status: 503,
        json: {
          code: "PROVIDER_RATE_LIMITED",
          message:
            "Translation unavailable: PROVIDER_RATE_LIMITED. Original evidence remains available.",
        },
      });
      return;
    }
    await route.fulfill({ json: data });
  });
  await page.goto("/analysis/ops");
  await expect(
    page
      .locator(".smart-summary")
      .getByRole("status")
      .filter({ hasText: "4 / 7" }),
  ).toBeVisible();
  await expect(
    page.getByRole("alert").filter({ hasText: "Translation unavailable" }),
  ).toBeVisible();
  await page.waitForTimeout(500);
  expect(translations).toBe(1);
});
