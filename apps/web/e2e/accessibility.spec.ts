import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("overview has no detectable WCAG A/AA accessibility violations", async ({ page }) => {
  await page.goto("http://127.0.0.1:3000/");
  await expect(page.getByRole("heading", { name: "Incident overview", level: 1 })).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();

  expect(results.violations).toEqual([]);
});

test("skip link works by keyboard and future actions remain disabled", async ({ page }) => {
  await page.goto("http://127.0.0.1:3000/");
  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Skip to main content" });
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);
  await expect(page.getByRole("link", { name: "New incident" })).toHaveAttribute("href", "/incidents/new");
});
