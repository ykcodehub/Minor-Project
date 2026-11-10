import { test, expect, devices } from "@playwright/test";
// Remote Google token/JWKS boundary is a fixture. Application redirects, cookies,
// DB state, signed JWT validation, session creation and dashboard are real.
for (const mode of ["desktop", "mobile"] as const) {
  test.describe(`Google OAuth ${mode}`, () => {
    test.use(
      mode === "mobile"
        ? {
            viewport: devices["Pixel 7"].viewport,
            userAgent: devices["Pixel 7"].userAgent,
            deviceScaleFactor: devices["Pixel 7"].deviceScaleFactor,
            isMobile: true,
            hasTouch: true,
          }
        : {},
    );
    test("OAuth starts on canonical host, verifies callback and opens authenticated dashboard", async ({
      page,
      context,
    }) => {
      let callback = "",
        state = "",
        code = "";
      let starts = 0,
        postStarts = 0;
      page.on("request", (request) => {
        if (new URL(request.url()).pathname === "/api/v1/auth/google/login")
          starts++;
        if (
          request.url().includes("/auth/google/start") &&
          request.method() === "POST"
        )
          postStarts++;
      });
      const cdp = await context.newCDPSession(page);
      await cdp.send("Fetch.enable", {
        patterns: [
          {
            urlPattern: "https://accounts.google.com/*",
            requestStage: "Request",
          },
        ],
      });
      cdp.on("Fetch.requestPaused", async (event) => {
        const url = new URL(event.request.url);
        callback = url.searchParams.get("redirect_uri")!;
        state = url.searchParams.get("state")!;
        code = "browser-fixture-" + url.searchParams.get("nonce")!;
        expect(url.searchParams.get("code_challenge_method")).toBe("S256");
        const html = `<html><body><h1>Synthetic Google boundary</h1><form action="${callback}" method="get"><input type="hidden" name="code" value="${code}"><input type="hidden" name="state" value="${state}"><button>Continue as synthetic Google user</button></form></body></html>`;
        await cdp.send("Fetch.fulfillRequest", {
          requestId: event.requestId,
          responseCode: 200,
          responseHeaders: [{ name: "Content-Type", value: "text/html" }],
          body: Buffer.from(html).toString("base64"),
        });
      });
      await page.goto("http://127.0.0.1:5174/sign-in");
      await page
        .getByRole("button", { name: "Continue with Google", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Synthetic Google boundary" }),
      ).toBeVisible();
      const cookie = (await context.cookies(callback)).find(
        (c) => c.name === "veriora_oauth",
      )!;
      expect(cookie).toBeTruthy();
      expect(cookie.domain).toBe("localhost");
      expect(cookie.httpOnly).toBe(true);
      expect(cookie.sameSite).toBe("Lax");
      expect(cookie.path).toBe("/api/v1/auth/google");
      expect(starts).toBe(1);
      expect(postStarts).toBe(0);
      await page
        .getByRole("button", { name: "Continue as synthetic Google user" })
        .click();
      await expect(page).toHaveURL("http://localhost:5174/dashboard");
      await expect(
        page.getByRole("heading", { name: "Pick up your document review." }),
      ).toBeVisible();
      const profile = await page.evaluate(
        async () => await (await fetch("/api/v1/me")).json(),
      );
      expect(profile.verified).toBe(true);
      expect(profile.is_guest).toBe(false);
      await page.reload();
      await expect(page).toHaveURL("http://localhost:5174/dashboard");
      const sessionCookie = (await context.cookies()).find(
        (c) => c.name === "veriora_session",
      )!;
      expect(sessionCookie.httpOnly).toBe(true);
      expect(sessionCookie.sameSite).toBe("Lax");
      await context.addCookies([cookie]);
      const duplicate = `${callback}?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`;
      const rejected = await page.request.get(duplicate);
      expect(rejected.status()).toBe(400); // State is never exchanged twice.
      await page.goto(duplicate);
      await expect(page).toHaveURL(
        "http://localhost:5174/sign-in?oauth=failed",
      );
      await page.reload();
      await expect(page).toHaveURL(
        "http://localhost:5174/sign-in?oauth=failed",
      );
      expect(starts).toBe(1); // Error rendering/refresh never restarts OAuth automatically.
    });
  });
}

test("callback without initiating browser cookie never establishes a session", async ({
  page,
}) => {
  const response = await page.goto(
    "http://localhost:5174/api/v1/auth/google/callback?code=synthetic-code&state=synthetic-state",
  );
  expect(response!.status()).toBe(200); // Safe sign-in error page after rejected callback.
  await expect(page).toHaveURL("http://localhost:5174/sign-in?oauth=failed");
  await expect(
    page.getByText(/Google sign-in could not be completed/),
  ).toBeVisible();
  const me = await page.request.get("http://localhost:5174/api/v1/me");
  expect(me.status()).toBe(401);
});
