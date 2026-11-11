import { test, expect } from "@playwright/test";

for (const mobile of [false, true])
  for (const partial of [false, true]) {
    test(`risk dashboard ${mobile ? "mobile" : "desktop"} ${partial ? "partial" : "complete"} shows honest severity and original PDF pages`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: mobile ? 390 : 1440, height: 900 });
      const quotes = [
        "The customer accepts unlimited liability.",
        "The customer grants an irrevocable license.",
        "Payment is due in thirty days.",
        "Data sharing requires consent.",
        "Termination requires notice.",
        "Disputes go to arbitration.",
        "The customer may request stored records.",
      ];
      const sections = Array.from({ length: 36 }, (_, i) => ({
        id: `sec-${i}`,
        ordinal: i,
        page: i < 18 ? 1 : 2,
        text: quotes[i - 18] || `Administrative record ${i}`,
      }));
      const findings = quotes.map((quote, i) => ({
        id: `f-${i}`,
        finding_id: `f-${i}`,
        category: [
          "RISK_NOTE",
          "RESTRICTION",
          "PAYMENT",
          "PRIVACY",
          "TERMINATION",
          "DISPUTE",
          "RIGHT",
        ][i],
        statement: quote,
        rationale: "Synthetic verified source term.",
        support_status: partial && i > 0 ? "AMBIGUOUS" : "SUPPORTED",
        qualifications: [],
        verification: { rationale: "Exact condition reviewed." },
        risk_assessment: {
          level:
            partial && i > 0
              ? "Needs Review"
              : i < 2
                ? "High"
                : i === 6
                  ? "Low"
                  : "Moderate",
          reason: "Explicit synthetic review rule.",
        },
        citations: [
          {
            source_id: "source",
            section_id: `sec-${18 + i}`,
            page: 2,
            start: 0,
            end: quote.length,
            quote,
            match_status: "EXACT",
          },
        ],
      }));
      const state = partial ? "PARTIAL_COMPLETION" : "COMPLETED";
      const source = {
        id: "source",
        kind: "upload",
        status: "READY",
        original_name: "Synthetic two-page agreement.pdf",
        sha256: "a".repeat(64),
        sections,
        coverage: { pages_total: 2, pages_extracted: 2, sections_total: 36 },
      };
      await page.route("**/api/v1/**", async (route) => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        let data: unknown = [];
        if (path === "/api/v1/me")
          data = {
            id: "synthetic",
            email: "fixture@example.com",
            is_guest: false,
            csrf_token: "fixture",
            language: "en",
            providers: [],
          };
        else if (path === "/api/v1/analyses/risk")
          data = {
            id: "risk",
            analysis_id: "risk",
            job_id: "job",
            status: state,
            source_ids: ["source"],
            sources: [source],
            coverage: { sections_total: 36, sections_processed: 36 },
            findings_count: 7,
            limitations: [],
          };
        else if (path === "/api/v1/jobs/job")
          data = {
            id: "job",
            state,
            stage: state,
            progress: {},
            result: {},
            error: partial ? "PROVIDER_OUTPUT_LIMIT" : null,
          };
        else if (path.endsWith("/summary"))
          data = {
            translation_ready: true,
            translations: {},
            summary: {
              level: partial ? "Not Determinable" : "High",
              rule: partial
                ? "Verification incomplete."
                : "Supported high-attention clause.",
              rule_version: "test",
              disclaimer: "Synthetic test only.",
              groups: {
                potential_risks: partial ? [findings[0]] : findings.slice(0, 2),
              },
              risk_groups: {
                High: partial ? [findings[0]] : findings.slice(0, 2),
                Moderate: partial ? [] : findings.slice(2, 6),
                Low: partial ? [] : [findings[6]],
              },
              risk_counts: {
                High: partial ? 1 : 2,
                Moderate: partial ? 0 : 4,
                Low: partial ? 0 : 1,
                Unassessed: 0,
              },
              counts: {
                verified: partial ? 1 : 7,
                retained: 7,
                excluded: partial ? 6 : 0,
              },
              coverage: { sections_processed: 36, sections_total: 36 },
              priority_index: partial ? null : 3,
              processing_state: state,
              failure_codes: partial ? ["PROVIDER_OUTPUT_LIMIT"] : [],
            },
          };
        else if (path.endsWith("/findings")) data = findings;
        else if (path.includes("/findings/"))
          data = findings.find((f) => path.endsWith(f.finding_id));
        else if (path === "/api/v1/sources/source") data = source;
        await route.fulfill({ json: data });
      });
      await page.goto("/analysis/risk");
      await expect(
        page.getByRole("tab", { name: "Summary", exact: true }),
      ).toHaveAttribute("aria-selected", "true");
      const chart = page.getByRole("img", {
        name: partial
          ? "Low: 0, Moderate: 0, High: 1"
          : "Low: 1, Moderate: 4, High: 2",
      });
      await expect(chart).toBeVisible();
      const critical = page.getByRole("region", {
        name: "Top critical issues",
      });
      await expect(critical).toBeVisible();
      expect(
        await critical
          .locator("article")
          .first()
          .evaluate((el) => getComputedStyle(el).borderLeftColor),
      ).toBe("rgb(179, 42, 58)");
      if (partial) {
        await expect(page.getByText(/6 findings require review/)).toBeVisible();
        await expect(
          page.getByText("Not Determinable", { exact: true }).first(),
        ).toBeVisible();
      } else
        await expect(page.getByText("3 / 3", { exact: true })).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBeTruthy();
      await page.screenshot({
        path: `../docs/verification-artifacts/risk-dashboard-${mobile ? "mobile" : "desktop"}-${partial ? "partial" : "complete"}.png`,
        fullPage: true,
      });
      await critical
        .getByRole("button", { name: /View exact source/ })
        .first()
        .click();
      await expect(
        page.getByRole("tab", { name: "Detailed Analysis", exact: true }),
      ).toHaveAttribute("aria-selected", "true");
      await expect(page.locator(".source-viewer mark")).toContainText(
        quotes[0],
      );
      await expect(page.locator(".viewer-toolbar")).toContainText("Page 2");
      await expect(page.locator(".viewer-toolbar")).toContainText("/ 2");
      await page.emulateMedia({ reducedMotion: "reduce" });
      expect(
        await page
          .locator(".finding-card.risk-item-high")
          .first()
          .evaluate((el) => getComputedStyle(el).animationName),
      ).toBe("none");
    });
  }
