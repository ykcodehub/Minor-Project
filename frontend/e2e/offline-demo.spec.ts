import { test, expect } from "@playwright/test";

for (const mobile of [false, true]) {
  test(`offline authored demo ${mobile ? "mobile" : "desktop"} works with API unavailable`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: mobile ? 390 : 1280, height: 900 });
    const calls: string[] = [];
    await page.route("**/api/**", async (route) => {
      calls.push(route.request().url());
      await route.abort();
    });
    await page.goto("/demo/offline");
    await expect(
      page.getByText("Offline demo — authored reference, not live AI"),
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "Summary", exact: true }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".risk-item-high")).toHaveCount(2);
    await expect(page.locator(".risk-segments")).toHaveAttribute(
      "aria-label",
      "Low: 1, Moderate: 4, High: 2",
    );
    await page
      .getByRole("button", { name: /View exact source.*Page 1/ })
      .first()
      .click();
    await expect(page.locator(".offline-source-selected")).toContainText(
      "unlimited liability",
    );
    await page.getByRole("button", { name: "Page 2", exact: true }).click();
    await expect(page.getByText("Page 2 / 2", { exact: true })).toBeVisible();
    await page
      .getByRole("tab", { name: "Saved demo question", exact: true })
      .click();
    await page
      .getByLabel("Offline question", { exact: true })
      .fill("When must invoices be paid?");
    await page.getByRole("button", { name: "Show saved answer" }).click();
    await expect(page.getByRole("blockquote")).toContainText(
      "Invoices must be paid within thirty days.",
    );
    await page
      .getByLabel("Offline question", { exact: true })
      .fill("What is the governing law?");
    await page.getByRole("button", { name: "Show saved answer" }).click();
    await expect(
      page.getByText(/No saved answer for this question/),
    ).toBeVisible();
    const download = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Export offline reference" })
      .click();
    expect((await download).suggestedFilename()).toContain("OFFLINE-AUTHORED");
    await page.getByTestId("global-language-toggle").click();
    await page.getByTestId("global-language-select").selectOption("hi");
    await expect(page.locator("html")).toHaveAttribute("lang", "hi");
    expect(calls).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
  });
}
