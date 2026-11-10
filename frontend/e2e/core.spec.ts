import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";
test("real guest upload, source inspection, deletion and session logout", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Understand every clause. Verify every claim.",
    }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/landing-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "Analyze a document", exact: true })
    .first()
    .click();
  await page.getByLabel("Choose document file").setInputFiles({
    name: "synthetic-service-agreement.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "SERVICE AGREEMENT\n\n1. Cancellation\nYou may cancel at any time. Fees already paid are non-refundable, except where required by law.\n\n2. Privacy\nWe share your data only with your consent, except for legally required disclosures.",
    ),
  });
  await page.getByRole("button", { name: "Save & inspect source" }).click();
  await expect(page).toHaveURL(/\/source\//, { timeout: 30000 });
  await expect(
    page
      .getByRole("heading", {
        name: "synthetic-service-agreement.txt",
        exact: true,
      })
      .first(),
  ).toBeVisible();
  await expect(page.locator(".source-text")).toContainText("SERVICE AGREEMENT");
  await expect(
    page.getByText(
      "AI analysis is unavailable until an administrator configures a provider. No analysis has been generated.",
    ),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/source-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({
    path: "test-results/source-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("link", { name: "Library", exact: true }).click();
  await page
    .getByRole("button", { name: "Delete synthetic-service-agreement.txt" })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("button", { name: "Delete document", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your next document starts here" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page
      .getByRole("banner")
      .getByRole("link", { name: "Sign in", exact: true }),
  ).toBeVisible();
});
test("registered account session, persistent settings and deletion", async ({
  page,
}) => {
  await page.goto("/sign-in");
  await page
    .getByRole("button", { name: "Create an account", exact: true })
    .click();
  const email = `ui-${Date.now()}@example.com`;
  await page.getByLabel("Email address").fill(email);
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(0);
  await page
    .getByRole("button", { name: "Send verification link", exact: true })
    .click();
  await expect(
    page.getByText("If this address can be registered", { exact: false }),
  ).toBeVisible();
  const deliveries = readFileSync(process.env.VERIORA_TEST_MAILBOX!, "utf8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
  const token = deliveries.findLast(
    (m) => m.email === email && m.purpose === "signup",
  ).token;
  await page.goto(`/sign-in?purpose=signup#token=${token}`);
  await expect(page.getByLabel("Create Password", { exact: true })).toHaveCount(
    0,
  );
  await page
    .getByRole("button", { name: "Verify email", exact: true })
    .first()
    .click();
  await expect(
    page.getByLabel("Create Password", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Create Password", { exact: true })
    .fill("Synthetic-password-2026!");
  await page
    .getByLabel("Confirm Password", { exact: true })
    .fill("Synthetic-password-2026!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByText("Account created. Sign in to continue."),
  ).toBeVisible();
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Synthetic-password-2026!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("/dashboard");
  await page.getByRole("link", { name: "Account", exact: true }).click();
  await page.getByLabel("Document retention").selectOption("7");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.getByText("Preferences saved")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Document retention")).toHaveValue("7");
  const sourceIds = await page.evaluate(async () => {
    const me = await (await fetch("/api/v1/me")).json();
    const ids: string[] = [];
    for (const [index, text] of [
      "Cancellation requires 30 days notice.",
      "Cancellation requires 60 days notice.",
    ].entries()) {
      const response = await fetch("/api/v1/sources/text", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": me.csrf_token,
        },
        body: JSON.stringify({ name: `Synthetic version ${index + 1}`, text }),
      });
      if (!response.ok) throw Error("Synthetic comparison intake failed");
      const source = await response.json();
      ids.push(source.source_id);
      for (let i = 0; i < 60; i++) {
        const job = await (await fetch(`/api/v1/jobs/${source.job_id}`)).json();
        if (job.state === "COMPLETED") break;
        if (job.state === "FAILED") throw Error("Synthetic extraction failed");
        await new Promise((r) => setTimeout(r, 250));
      }
    }
    return ids;
  });
  await page.goto("/compare");
  await page.getByLabel("Earlier / first source").selectOption(sourceIds[0]);
  await page.getByLabel("Later / second source").selectOption(sourceIds[1]);
  await page
    .getByRole("button", { name: "Compare sources", exact: true })
    .click();
  await expect(page.locator(".diff-row.changed")).toContainText("30 days");
  await expect(page.locator(".diff-row.changed")).toContainText("60 days");
  await page.screenshot({
    path: "test-results/comparison-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.goto("/forgot-password");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByRole("button", { name: "Send recovery instructions" })
    .click();
  await expect(
    page.getByText("If this account can be recovered", { exact: false }),
  ).toBeVisible();
  const resetMail = readFileSync(process.env.VERIORA_TEST_MAILBOX!, "utf8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line))
    .findLast((m) => m.email === email && m.purpose === "recover");
  await page.goto(`/sign-in?purpose=recover#token=${resetMail.token}`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Replacement-browser-password-2026!");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(
    page.getByText("Password updated. Sign in with your new password."),
  ).toBeVisible();
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Replacement-browser-password-2026!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("/dashboard");
  await page.goto("/settings");
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page
    .getByRole("button", { name: "Delete my account and data" })
    .click();
  await expect(page).toHaveURL("/sign-in");
  await expect(
    page
      .getByRole("banner")
      .getByRole("link", { name: "Sign in", exact: true }),
  ).toBeVisible();
});
test("mobile landing and intake fit a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Understand every clause. Verify every claim.",
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/landing-mobile.png",
    fullPage: true,
  });
  await page.goto("/analyze?mode=text");
  await expect(page.getByLabel("Original document text")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
