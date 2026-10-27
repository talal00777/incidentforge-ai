import { expect, test } from "@playwright/test";

test("evidence route is protected by the existing account session", async ({ page }) => {
  await page.goto("/incidents/00000000-0000-0000-0000-000000000001/sources");
  await expect(page.getByRole("heading", { name: "Incident evidence" })).toBeVisible();
  await expect(page.getByLabel("Log files")).toBeVisible();
});
