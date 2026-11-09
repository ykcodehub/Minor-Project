import { test, expect } from "@playwright/test";
test("header language persists through navigation and reload without AI requests", async ({
  page,
}) => {
  let aiRequests = 0;
  page.on("request", (request) => {
    if (
      /\/(translations|questions)(?:\?|$)/.test(request.url()) &&
      request.method() === "POST"
    )
      aiRequests++;
  });
  await page.goto("/analyze");
  await page.evaluate(async () => {
    const response = await fetch("/api/v1/auth/guest", { method: "POST" });
    if (!response.ok) throw Error("Guest setup failed");
  });
  await page.reload();
  await expect(page.getByTestId("global-language-toggle")).toBeVisible();
  await page.getByTestId("global-language-toggle").click();
  await page.getByTestId("global-language-select").selectOption("hi");
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(
    page
      .getByRole("banner")
      .getByRole("link", { name: "विश्लेषण करें", exact: true }),
  ).toBeVisible();
  await page.getByRole("banner").locator('a[href="/library"]').click();
  await expect(page).toHaveURL("/library");
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect
    .poll(async () =>
      page.evaluate(
        async () => (await (await fetch("/api/v1/me")).json()).language,
      ),
    )
    .toBe("hi");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await page.getByTestId("global-language-toggle").click();
  await page.getByTestId("global-language-select").selectOption("hinglish");
  await expect(page.locator("html")).toHaveAttribute("lang", "hi-Latn");
  await page.getByRole("banner").locator('a[href="/dashboard"]').click();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi-Latn");
  await page.getByTestId("global-language-toggle").click();
  await page.getByTestId("global-language-select").selectOption("en");
  await expect(
    page
      .getByRole("banner")
      .getByRole("link", { name: "Analyze", exact: true }),
  ).toBeVisible();
  expect(aiRequests).toBe(0);
});
