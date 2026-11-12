import { test, expect } from "@playwright/test";

test("isolated running app uploads a real two-page synthetic PDF without AI", async ({
  page,
}) => {
  test.skip(
    !process.env.VERIORA_LOCAL_SYNTHETIC_PDF,
    "Requires the explicitly isolated local PDF fixture.",
  );
  await page.goto("/");
  await page
    .getByRole("link", { name: "Analyze a document", exact: true })
    .first()
    .click();
  await page
    .getByLabel("Choose document file")
    .setInputFiles(process.env.VERIORA_LOCAL_SYNTHETIC_PDF!);
  await page.getByRole("button", { name: "Save & inspect source" }).click();
  await expect(page).toHaveURL(/\/source\//, { timeout: 30000 });
  await expect(
    page
      .locator(".source-text")
      .filter({ hasText: "Customer must pay" })
      .first(),
  ).toContainText("Customer", {
    timeout: 30000,
  });
  await expect(
    page.getByText(
      "AI analysis is unavailable until an administrator configures a provider. No analysis has been generated.",
    ),
  ).toBeVisible();
  const result = await page.evaluate(async () => {
    const id = location.pathname.split("/").pop();
    return (await fetch(`/api/v1/sources/${id}`)).json();
  });
  expect(result.coverage.pages_total).toBe(2);
  expect(result.coverage.pages_extracted).toBe(2);
  await page.screenshot({
    path: "test-results/local-two-page-pdf.png",
    fullPage: true,
  });
});
