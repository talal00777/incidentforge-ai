import { expect, test } from "@playwright/test";

test("evidence route requires an authenticated session before showing upload controls", async ({ page }) => {
  const incidentId = "00000000-0000-0000-0000-000000000001";
  await page.goto(`/incidents/${incidentId}/sources`);
  await expect(page.getByRole("heading", { name: "Incident evidence" })).toBeVisible();
  await expect(page.getByRole("link", { name: "sign in" })).toBeVisible();
  await expect(page.getByLabel("Log files")).toHaveCount(0);

  const apiResponse = await page.request.get(`/api/v1/incidents/${incidentId}/sources`);
  expect([401, 403]).toContain(apiResponse.status());
});
