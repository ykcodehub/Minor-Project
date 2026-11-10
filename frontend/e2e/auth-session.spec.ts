import { test, expect } from "@playwright/test";

test("successful login response without a browser session never opens dashboard", async ({
  page,
}) => {
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({ status: 200, json: { id: "synthetic" } }),
  );
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ status: 401, json: { message: "Please sign in." } }),
  );
  await page.goto("/sign-in");
  await page.getByLabel("Email address").fill("synthetic@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Synthetic-password-2026!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByText(/Your session could not be restored/),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/sign-in$/);
});

test("anonymous protected route redirects to sign-in without creating a guest", async ({
  page,
}) => {
  let guests = 0;
  page.on("request", (r) => {
    if (r.url().endsWith("/auth/guest")) guests++;
  });
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/sign-in$/);
  expect(guests).toBe(0);
});

test("expired server session can still sign out and clears the client identity", async ({
  page,
}) => {
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({
      status: 200,
      json: {
        id: "synthetic-expired",
        email: "synthetic@example.com",
        is_guest: false,
        language: "en",
        providers: [],
        retention_days: 30,
        csrf_token: "synthetic",
      },
    }),
  );
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ status: 401, json: { message: "Session expired." } }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(
    page
      .getByRole("banner")
      .getByRole("link", { name: "Sign in", exact: true }),
  ).toBeVisible();
});

test("invalid email password returns expected401 without navigating away", async ({
  page,
}) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email address").fill("missing-account@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Wrong-password-2026!");
  const rejected = page.waitForResponse(
    (r) => r.url().endsWith("/auth/login") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  expect((await rejected).status()).toBe(401);
  await expect(page.getByText("Email or password is incorrect.")).toBeVisible();
  await expect(page).toHaveURL(/\/sign-in$/);
});
