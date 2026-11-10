import { test, expect } from "@playwright/test";
import path from "node:path";

test("live PostgreSQL and configured AI: PDF → evidence → question → reports → history", async ({
  page,
}) => {
  test.skip(
    process.env.VERIORA_LIVE_E2E !== "1",
    "Explicit opt-in required: uses configured AI and preserves synthetic PostgreSQL records.",
  );
  test.setTimeout(300000);
  page.on("pageerror", (error) =>
    console.log("UI runtime error:", error.name, error.message),
  );
  test.skip(
    !process.env.VERIORA_LIVE_EMAIL || !process.env.VERIORA_LIVE_PASSWORD,
    "Requires an already email-verified synthetic account; no verification bypass.",
  );
  await page.goto("/sign-in");
  await page.getByLabel("Email address").fill(process.env.VERIORA_LIVE_EMAIL!);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.VERIORA_LIVE_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("/dashboard");
  await page.goto("/analyze");
  await page
    .getByLabel("Choose document file")
    .setInputFiles(
      path.resolve("../backend/tests/fixtures/synthetic_contract.pdf"),
    );
  await page
    .getByRole("combobox", { name: /AI provider/ })
    .selectOption("gemini");
  await page
    .getByLabel(
      "I authorize this document to be processed by the selected AI provider.",
    )
    .check();
  await page
    .getByRole("button", { name: "Upload & analyze", exact: true })
    .click();
  await expect(page).toHaveURL(/\/analysis\//, { timeout: 60000 });
  console.log("Live step: source uploaded and analysis queued");
  await page
    .getByRole("tab", { name: "Detailed Analysis", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "View evidence" }).first(),
  ).toBeVisible({ timeout: 180000 });
  await page.getByRole("button", { name: "View evidence" }).first().click();
  await expect(page.locator(".source-text mark")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Evidence Passport" }),
  ).toBeVisible();
  await expect(page.locator(".source-location")).toContainText(
    /page|Privacy|Payment|Cancellation/i,
  );
  await page.screenshot({
    path: "test-results/live-workspace.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Ask Veriora" }).click();
  await page
    .getByLabel("Your document question")
    .fill("When must invoices be paid?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator(".answer")).toContainText(/30|thirty/i, {
    timeout: 90000,
  });
  await expect(page.locator(".citation-chip").first()).toBeVisible();
  await page.locator(".citation-chip").first().click();
  await expect(page.locator(".source-text mark")).toBeVisible();
  for (const name of ["Manifest", "PDF report"]) {
    const pending = page.waitForEvent("download");
    await page.getByRole("button", { name, exact: true }).click();
    expect((await pending).suggestedFilename()).toMatch(/\.(json|pdf)$/);
  }
  const analysisURL = page.url();
  await page.reload();
  await page.getByRole("tab", { name: "Ask Veriora" }).click();
  await expect(page.locator(".answer")).toContainText(/30|thirty/i);
  await page.goto("/dashboard");
  await expect(
    page.getByRole("heading", { name: "Recent documents" }),
  ).toBeVisible();
  await expect(page.locator(".dashboard-counts")).toContainText("1");
  await page.goto("/library");
  await expect(
    page.getByRole("link", { name: "synthetic_contract.pdf", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page
      .getByRole("banner")
      .getByRole("link", { name: "Sign in", exact: true }),
  ).toBeVisible();
  console.log(
    "Live synthetic workflow passed; PostgreSQL test records preserved. Analysis route:",
    new URL(analysisURL).pathname,
  );
});
