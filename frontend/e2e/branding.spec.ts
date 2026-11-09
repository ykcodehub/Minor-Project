import { test, expect } from "@playwright/test";
test("missing logo has a safe fallback and footer uses the current year", async ({
  page,
}) => {
  await page.route("**/logo.png", (route) =>
    route.fulfill({ status: 404, body: "" }),
  );
  await page.goto("/");
  await expect(page.locator(".brand-fallback").first()).toBeVisible();
  await expect(page.locator(".brand-mark img").first()).not.toBeVisible();
  await expect(page.getByRole("contentinfo")).toContainText(
    `© ${new Date().getFullYear()} Veriora · All rights reserved.`,
  );
  await page.setViewportSize({ width: 375, height: 812 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("brand has no trailing dot and navigation supports focus and reduced motion", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/analyze");
  // The decorative fallback contributes V to textContent, including when hidden.
  await expect(page.locator("header .brand")).toHaveText(/^(?:V)?veriora$/);
  await expect(page.locator("footer .brand")).toHaveText("veriora");
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  const analyze = nav.getByRole("link", { name: "Analyze", exact: true });
  await expect(analyze).toHaveAttribute("aria-current", "page");
  await analyze.focus();
  await expect(analyze).toBeFocused();
  await expect(analyze).toHaveCSS("outline-style", "solid");
  await expect(analyze).toHaveCSS("transition-property", "none");
  await page.keyboard.press("Tab");
  await expect(
    nav.getByRole("link", { name: "Library", exact: true }),
  ).toBeFocused();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
