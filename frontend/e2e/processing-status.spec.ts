import { test, expect } from "@playwright/test";
test("queued source polling pauses honestly and can be resumed", async ({
  page,
}) => {
  let reads = 0;
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({
      status: 200,
      json: {
        id: "synthetic",
        email: "synthetic@example.com",
        is_guest: false,
        language: "en",
        providers: [],
        retention_days: 30,
        csrf_token: "fixture",
      },
    }),
  );
  await page.route("**/api/v1/sources/queued-source", (route) => {
    reads++;
    return route.fulfill({
      status: 200,
      json: {
        id: "queued-source",
        original_name: "queued.txt",
        status: "QUEUED",
        job_state: "QUEUED",
        kind: "text",
        sha256: "a".repeat(64),
        captured_at: new Date().toISOString(),
        sections: [],
      },
    });
  });
  await page.clock.install();
  await page.goto("/source/queued-source");
  await expect(
    page.getByRole("heading", { name: "queued.txt", exact: true }).first(),
  ).toBeVisible();
  await page.clock.fastForward(601000);
  await expect(
    page.getByText(/Status checks paused after 10 minutes/),
  ).toBeVisible();
  const pausedReads = reads;
  await page.clock.fastForward(60000);
  expect(reads).toBe(pausedReads);
  await page
    .getByRole("button", { name: "Refresh status", exact: true })
    .click();
  await expect(
    page.getByText(/Status checks paused after 10 minutes/),
  ).not.toBeVisible();
  await expect.poll(() => reads).toBeGreaterThan(pausedReads);
});
