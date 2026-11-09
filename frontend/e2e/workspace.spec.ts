import { test, expect } from "@playwright/test";
// Synthetic API responses isolate trust-label and source-navigation behavior.
// Live provider quality is deliberately outside this browser fixture.
test("synthetic workspace links evidence, rejects invalid citation, abstains and exports", async ({
  page,
}) => {
  const text =
    "𝒙 Cancellation takes effect at the end of the billing period, except where required by law.";
  const source = {
    id: "synthetic-source",
    original_name: "Synthetic agreement.txt",
    kind: "text",
    status: "READY",
    sha256: "a".repeat(64),
    captured_at: "2026-11-08T09:00:00Z",
    sections: [
      {
        id: "synthetic-section",
        ordinal: 0,
        text,
        page: null,
        heading: "Cancellation",
      },
    ],
  };
  const citation = {
    source_id: source.id,
    section_id: "synthetic-section",
    quote: Array.from(text).slice(2).join(""),
    start: 2,
    end: Array.from(text).length,
    page: null,
    match_status: "EXACT",
  };
  const finding = {
    finding_id: "supported-finding",
    statement:
      "Cancellation takes effect after the billing period, subject to legal exceptions.",
    category: "OBLIGATION",
    rationale:
      "The clause defines the effective cancellation date and its exception.",
    qualifications: ["Except where required by law."],
    support_status: "SUPPORTED",
    citations: [citation],
    verification: { method: "Synthetic verifier fixture" },
    provider: "synthetic",
    model: "test-only",
  };
  const invalid = {
    ...finding,
    finding_id: "invalid-finding",
    statement: "Synthetic rejected interpretation.",
    support_status: "UNSUPPORTED",
    citations: [{ ...citation, page: 99, match_status: "INVALID" }],
  };
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    let data: unknown;
    const path = url.pathname;
    if (path === "/api/v1/me" || path === "/api/v1/me/language")
      data = {
        id: "synthetic-user",
        email: "fixture@example.com",
        is_guest: false,
        csrf_token: "synthetic-csrf",
        retention_days: 30,
        providers: [],
      };
    else if (path === "/api/v1/analyses/synthetic-analysis")
      data = {
        analysis_id: "synthetic-analysis",
        status: "COMPLETED",
        job_id: "synthetic-job",
        source_ids: [source.id],
        sources: [source],
        coverage: {
          sections_total: 1,
          sections_processed: 1,
          chunks_total: 1,
          chunks_processed: 1,
          warnings: [],
        },
        limitations: ["Synthetic browser fixture only."],
        findings_count: 2,
      };
    else if (path.endsWith("/summary"))
      data = {
        language: url.searchParams.get("language") || "en",
        translation_ready: true,
        translations: {
          "supported-finding": {
            statement:
              url.searchParams.get("language") === "hi"
                ? "रद्दीकरण अवधि के अंत में प्रभावी होता है।"
                : url.searchParams.get("language") === "hinglish"
                  ? "Cancellation billing period ke end par hota hai."
                  : finding.statement,
            rationale: finding.rationale,
            qualifications: finding.qualifications,
          },
        },
        summary: {
          level: "Not Determinable",
          rule: "Unresolved synthetic finding.",
          rule_version: "attention-1.0",
          disclaimer: "Synthetic fixture only.",
          groups: {
            benefits: [],
            obligations: [finding],
            restrictions: [],
            potential_risks: [],
            exceptions: [finding],
          },
        },
      };
    else if (path.endsWith("/findings")) data = [finding, invalid];
    else if (path === "/api/v1/jobs/synthetic-job")
      data = {
        id: "synthetic-job",
        state: "COMPLETED",
        stage: "COMPLETED",
        progress: {},
      };
    else if (path === "/api/v1/sources/synthetic-source") data = source;
    else if (path.endsWith("/questions"))
      data =
        route.request().method() === "POST"
          ? {
              answer: "I cannot confirm this from the available document.",
              citations: [],
              limitations: ["Missing evidence."],
            }
          : [];
    else if (path.endsWith("/exports")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "Content-Disposition":
            'attachment; filename="synthetic-manifest.json"',
        },
        body: JSON.stringify({
          analysis_id: "synthetic-analysis",
          sources: [source],
        }),
      });
      return;
    } else {
      await route.fulfill({
        status: 404,
        json: { message: "Unknown synthetic fixture endpoint" },
      });
      return;
    }
    await route.fulfill({ status: 200, json: data });
  });
  await page.goto("/analysis/synthetic-analysis");
  await expect(
    page.getByRole("tab", { name: "Summary", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("heading", { name: "Document summary" }),
  ).toBeVisible();
  await expect(page.getByTestId("processing-coverage")).not.toBeVisible();
  await page
    .getByRole("tab", { name: "Detailed Analysis", exact: true })
    .click();
  await expect(page.getByTestId("processing-coverage")).toBeVisible();
  expect(
    await page.evaluate(() => {
      const coverage = document.querySelector(
        '[data-testid="processing-coverage"]',
      )!;
      const grid = document.querySelector(".workspace-grid")!;
      return (
        coverage.getBoundingClientRect().top >=
        grid.getBoundingClientRect().bottom
      );
    }),
  ).toBe(true);
  await expect(
    page.getByText("Verified against source", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Source reference invalid", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Summary", exact: true }).click();
  await page.screenshot({
    path: "test-results/summary-desktop.png",
    fullPage: true,
  });
  await page.getByTestId("global-language-toggle").click();
  await page.getByTestId("global-language-select").selectOption("hi");
  await expect(
    page.getByRole("heading", { name: "दस्तावेज़ का सारांश" }),
  ).toBeVisible();
  await page.locator(".clause-context summary").first().click();
  await expect(page.locator(".summary-clause blockquote").first()).toHaveText(
    citation.quote,
  );
  await page.getByTestId("global-language-toggle").click();
  await page.getByTestId("global-language-select").selectOption("hinglish");
  await expect(
    page.getByRole("heading", { name: "Document ka summary" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /Original source dekhein/ })
    .first()
    .click();
  await expect(page.locator(".source-text mark")).toHaveText(citation.quote);
  await page.getByTestId("global-language-toggle").click();
  await page.getByTestId("global-language-select").selectOption("en");
  await page.getByRole("button", { name: "View evidence" }).first().click();
  await expect(page.locator(".source-text mark")).toHaveText(citation.quote);
  await expect(page.locator(".source-text")).toHaveText(text);
  await expect(
    page.getByRole("heading", { name: "Evidence Passport" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/workspace-synthetic-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "View evidence" }).nth(1).click();
  await expect(page.locator(".source-text mark")).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("tab", { name: "Summary", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page
    .getByRole("tab", { name: "Detailed Analysis", exact: true })
    .click();
  await page.getByRole("tab", { name: "Ask Veriora" }).click();
  await page
    .getByLabel("Your document question")
    .fill("Does this prove legal compliance?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(
    page.getByText("I cannot confirm this from the available document.", {
      exact: true,
    }),
  ).toBeVisible();
  const pendingDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Manifest", exact: true }).click();
  expect((await pendingDownload).suggestedFilename()).toContain(".json");
  await page.getByRole("tab", { name: "Findings", exact: true }).click();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole("tab", { name: "Insights", exact: true }).click();
  await page.getByRole("button", { name: "View evidence" }).first().click();
  await expect(page.locator(".source-text mark")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/workspace-synthetic-mobile.png",
    fullPage: true,
  });
});
