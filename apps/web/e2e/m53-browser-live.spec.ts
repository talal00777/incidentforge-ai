/**
 * Read-only live M5.3 acceptance against the actual Django API and Next.js UI.
 * Requires a pre-existing, finalized postmortem and operator-provided credentials.
 * NEVER creates users, versions, investigations or AI requests.
 * Skips cleanly when not configured; see docs/M5_3_BROWSER_ACCEPTANCE.md.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

const baseURL = process.env.IF_M53_BASE_URL ?? "http://localhost:3000";
const email = process.env.IF_M53_EMAIL ?? "";
const password = process.env.IF_M53_PASSWORD ?? "";
const incidentId = process.env.IF_M53_INCIDENT_ID ?? "";
const versionId = process.env.IF_M53_VERSION_ID ?? "";
const oldVersionId = process.env.IF_M53_OLD_VERSION_ID ?? "";
const otherEmail = process.env.IF_M53_OTHER_EMAIL ?? "";
const otherPassword = process.env.IF_M53_OTHER_PASSWORD ?? "";
const configured = Boolean(email && password && incidentId && versionId);
const resource = `/api/v1/incidents/${encodeURIComponent(incidentId)}/reports/${encodeURIComponent(versionId)}`;
const downloadUrl = (format: "pdf" | "json") => `${resource}/download?export_format=${format}`;

/** Extract the exact canonical content JSON bytes from the exported envelope. */
function canonicalContentFromExport(buffer: Buffer): string {
  const raw = buffer.toString("utf8").trimEnd();
  const prefix = '{"content":';
  if (!raw.startsWith(prefix)) throw new Error("Export is not canonical JSON (content not first)");
  let depth = 0;
  let insideString = false;
  let escaped = false;
  for (let i = prefix.length; i < raw.length; i += 1) {
    const char = raw[i];
    if (insideString) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') insideString = false;
    } else if (char === '"') insideString = true;
    else if (char === "{" || char === "[") depth += 1;
    else if (char === "}" || char === "]") {
      depth -= 1;
      if (depth === 0) return raw.slice(prefix.length, i + 1);
    }
  }
  throw new Error("Could not locate canonical content in JSON export");
}

async function login(page: import("@playwright/test").Page, userEmail: string, userPassword: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(userEmail);
  await page.getByLabel("Password").fill(userPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/incidents(?:\/)?$/);
}

test.describe("M5.3 live-browser acceptance (read-only)", () => {
  test.skip(!configured, "Set IF_M53_EMAIL, IF_M53_PASSWORD, IF_M53_INCIDENT_ID, IF_M53_VERSION_ID to run live tests.");

  test.beforeEach(async ({ page }) => {
    await login(page, email, password);
  });

  test("PDF and JSON browser downloads match saved immutable version and repeat", async ({ page }) => {
    await page.goto(`/incidents/${incidentId}/reports/${versionId}`);
    await expect(page.getByRole("link", { name: "Download PDF" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Download JSON" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Incident summary" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Human assessment" })).toBeVisible();

    const detailResponse = await page.request.get(resource);
    expect(detailResponse.status()).toBe(200);
    const detail = await detailResponse.json();

    const [jsonDownload] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("link", { name: "Download JSON" }).click(),
    ]);
    const jsonBuffer = readFileSync(await jsonDownload.path());
    const exported = JSON.parse(jsonBuffer.toString("utf8"));
    expect(jsonDownload.suggestedFilename()).toContain(`v${detail.version}-${versionId}.json`);
    expect(exported.export_schema_version).toBe("1.0");
    expect(exported.postmortem_version.id).toBe(versionId);
    expect(exported.postmortem_version.number).toBe(detail.version);
    expect(exported.content).toEqual(detail.content);
    const actualSha = createHash("sha256").update(canonicalContentFromExport(jsonBuffer), "utf8").digest("hex");
    expect(actualSha).toBe(detail.content_sha256);
    expect(exported.postmortem_version.content_sha256).toBe(detail.content_sha256);

    const [pdfDownload] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("link", { name: "Download PDF" }).click(),
    ]);
    const firstPdf = readFileSync(await pdfDownload.path());
    expect(pdfDownload.suggestedFilename()).toContain(`v${detail.version}-${versionId}.pdf`);
    expect(firstPdf.subarray(0, 5).toString()).toBe("%PDF-");
    expect(firstPdf.length).toBeGreaterThan(2000);

    const secondPdfResponse = await page.request.get(downloadUrl("pdf"));
    const secondJsonResponse = await page.request.get(downloadUrl("json"));
    expect(secondPdfResponse.status()).toBe(200);
    expect(secondPdfResponse.headers()["content-type"]).toContain("application/pdf");
    expect(secondPdfResponse.headers()["cache-control"]).toBe("private, no-store");
    expect(Buffer.from(await secondPdfResponse.body()).equals(firstPdf)).toBe(true);
    expect(secondJsonResponse.status()).toBe(200);
    expect(Buffer.from(await secondJsonResponse.body()).equals(jsonBuffer)).toBe(true);
  });

  test("unsupported formats and anonymous requests cannot export a report", async ({ page, browser }) => {
    const bad = await page.request.get(`${resource}/download?export_format=html`);
    expect(bad.status()).toBe(400);
    expect((await bad.json()).code).toBe("invalid_export_format");

    const anonymous = await browser.newContext({ baseURL });
    try {
      const forbiddenPdf = await anonymous.request.get(downloadUrl("pdf"));
      const forbiddenJson = await anonymous.request.get(downloadUrl("json"));
      expect([401, 403]).toContain(forbiddenPdf.status());
      expect([401, 403]).toContain(forbiddenJson.status());
      expect((await forbiddenPdf.body()).subarray(0, 5).toString()).not.toBe("%PDF-");
    } finally {
      await anonymous.close();
    }
  });

  test("historical report still opens and its content matches its own JSON export", async ({ page }) => {
    test.skip(!oldVersionId, "Set IF_M53_OLD_VERSION_ID to check a second immutable version.");
    const oldResource = `/api/v1/incidents/${encodeURIComponent(incidentId)}/reports/${encodeURIComponent(oldVersionId)}`;
    const oldDetailResponse = await page.request.get(oldResource);
    const newestDetailResponse = await page.request.get(resource);
    expect(oldDetailResponse.status()).toBe(200);
    expect(newestDetailResponse.status()).toBe(200);
    const oldDetail = await oldDetailResponse.json();
    const newest = await newestDetailResponse.json();
    expect(oldDetail.version).toBeLessThan(newest.version);
    const exported = await page.request.get(`${oldResource}/download?export_format=json`);
    expect(exported.status()).toBe(200);
    const payload = await exported.json();
    expect(payload.content).toEqual(oldDetail.content);
    expect(payload.postmortem_version.content_sha256).toBe(oldDetail.content_sha256);
    await page.goto(`/incidents/${incidentId}/reports/${oldVersionId}`);
    await expect(page.getByRole("link", { name: "Download JSON" })).toBeVisible();
    await expect(page.getByText(`Version ${oldDetail.version}`)).toBeVisible();
  });

  test("a different signed-in user cannot access incident-owned report", async ({ browser }) => {
    test.skip(!otherEmail || !otherPassword, "Set IF_M53_OTHER_EMAIL and IF_M53_OTHER_PASSWORD for cross-account authorization.");
    const other = await browser.newContext({ baseURL });
    try {
      const otherPage = await other.newPage();
      await login(otherPage, otherEmail, otherPassword);
      const detail = await otherPage.request.get(resource);
      const pdf = await otherPage.request.get(downloadUrl("pdf"));
      const json = await otherPage.request.get(downloadUrl("json"));
      expect(detail.status()).toBe(404);
      expect(pdf.status()).toBe(404);
      expect(json.status()).toBe(404);
    } finally {
      await other.close();
    }
  });
});
