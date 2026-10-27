import { expect, test } from "@playwright/test";

test("register, create, update and delete an owned incident", async ({ page }) => {
  const email = `m1-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.org`;
  await page.goto("http://localhost:3000/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("unique-high-entropy-phrase-8842");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/incidents$/);
  await page.getByRole("link", { name: "New incident" }).click();
  await page.getByLabel("Title").fill("Checkout latency after deploy");
  await page.getByLabel("Service").fill("checkout-api");
  await page.getByRole("button", { name: "Create incident" }).click();
  await expect(page).toHaveURL(/\/incidents\/[0-9a-f-]+$/);
  await page.getByRole("link", { name: "Evidence & sources" }).click();
  await expect(page).toHaveURL(/\/incidents\/[0-9a-f-]+\/sources$/);
  await expect(page.getByRole("heading", { name: "Incident evidence" })).toBeVisible();
  await expect(page.getByLabel("Log files")).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Incident details" })).toBeVisible();
  await page.getByLabel("Status").selectOption("investigating");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByLabel("Status")).toHaveValue("investigating");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete incident" }).click();
  await expect(page).toHaveURL(/\/incidents$/);
  await expect(page.getByText("No matching incidents.")).toBeVisible();
});
