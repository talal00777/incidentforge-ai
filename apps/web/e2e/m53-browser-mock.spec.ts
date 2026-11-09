/**
 * M5.3 deterministic UI acceptance checks against the actual Next.js pages.
 * The /api/v1/* requests are intercepted in the browser: no accounts, database
 * records, external AI API requests, or sensitive user data are modified.
 * These do not replace live-backend download and authorization checks.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page, type Route } from "@playwright/test";

const incidentId = "11111111-1111-4111-8111-111111111111";
const investigationId = "22222222-2222-4222-8222-222222222222";
const firstId = "33333333-3333-4333-8333-333333333333";
const secondId = "44444444-4444-4444-8444-444444444444";
const evidenceId = "55555555-5555-4555-8555-555555555555";
const eventId = "66666666-6666-4666-8666-666666666666";
const sourceId = "77777777-7777-4777-8777-777777777777";
const userId = "88888888-8888-4888-8888-888888888888";
const apiRoot = `/api/v1/incidents/${incidentId}`;
const createdAt = "2026-11-08T02:12:00Z";
const pdf = readFileSync(path.join(__dirname, "fixtures", "m53-synthetic.pdf"));

function frozenVersion(id: string, number: number, summary: string) {
  return {
    id,
    version: number,
    investigation_id: investigationId,
    review_revision_number: number,
    content_sha256: String(number).repeat(64),
    created_by_id: userId,
    created_at: createdAt,
    content: {
      schema_version: "1.0",
      incident: { id: incidentId, title: "Synthetic gateway timeout" },
      ai: {
        investigation_id: investigationId,
        created_at: createdAt,
        provider: "synthetic",
        model_id: "mock-no-external-call",
        prompt_profile: "few_shot",
        prompt_version: "1.0",
        response_schema_version: "1.0",
        generation: { temperature: 0.2, max_output_tokens: 1024 },
        usage: { input_tokens: 10, output_tokens: 15 },
        consent_accepted_at: createdAt,
        evidence_snapshot: {
          id: evidenceId,
          sha256: "a".repeat(64),
          selection_version: "1.0",
          privacy_policy_version: "1.0",
        },
        findings: {
          schema_version: "1.0",
          incident_summary: summary,
          observed_facts: [{ statement: "Gateway returned a timeout.", event_ids: [eventId] }],
          hypotheses: [
            {
              title: "Upstream timeout",
              status: "plausible_unconfirmed",
              supporting_event_ids: [eventId],
              contradicting_event_ids: [],
              alternative_explanations: ["Network congestion"],
              further_checks: [],
            },
          ],
          suggested_actions: [
            { action: "Check upstream latency metrics", safety: "read_only", rationale_event_ids: [eventId] },
          ],
          limitations: ["The cause remains unconfirmed."],
        },
      },
      human: {
        revision: number,
        status: "reviewed",
        author_id: userId,
        reviewed_at: createdAt,
        impact_notes: "Intermittent test checkouts failed.",
        remediation_notes: "Review retry budgets.",
        hypotheses: [
          { index: 0, decision: "accepted_as_working_hypothesis", note: "Correlated with gateway events." },
        ],
      },
      evidence_manifest: [
        {
          event_id: eventId,
          source_id: sourceId,
          source_name: "synthetic-gateway.log",
          source_sha256: "b".repeat(64),
          source_lines: [1, 2],
          occurred_at: createdAt,
          service: "gateway",
        },
      ],
      timeline: [{ event_id: eventId, occurred_at: createdAt, service: "gateway", severity: "ERROR" }],
    },
  };
}

const first = frozenVersion(firstId, 1, "Version one: gateway timeout observed.");
const second = frozenVersion(secondId, 2, "Version two: new human-review revision.");

function jsonResponse(route: Route, value: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(value),
  });
}

async function installSyntheticApi(page: Page) {
  let hasSecondVersion = false;
  let finalizationPayload: unknown;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const resource = url.pathname;

    if (resource === "/api/v1/auth/me") {
      return jsonResponse(route, { id: userId, email: "synthetic@example.invalid", first_name: "Test", last_name: "User" });
    }
    if (resource === "/api/v1/auth/csrf") return jsonResponse(route, { csrf_token: "synthetic-token" });
    if (resource === `${apiRoot}/investigations`) {
      return jsonResponse(route, [{ id: investigationId, model_id: "mock-no-external-call", created_at: createdAt }]);
    }
    if (resource === `${apiRoot}/investigations/${investigationId}/review`) {
      return jsonResponse(route, {
        revision: 2,
        status: "reviewed",
        hypotheses: [{ decision: "accepted_as_working_hypothesis" }],
      });
    }
    if (resource === `${apiRoot}/reports` && request.method() === "GET") {
      return jsonResponse(route, (hasSecondVersion ? [second, first] : [first]).map((item) => ({
        id: item.id,
        version: item.version,
        investigation_id: item.investigation_id,
        review_revision_number: item.review_revision_number,
        content_sha256: item.content_sha256,
        created_by_id: item.created_by_id,
        created_at: item.created_at,
      })));
    }
    if (resource === `${apiRoot}/reports` && request.method() === "POST") {
      finalizationPayload = request.postDataJSON();
      if (request.headers()["x-csrftoken"] !== "synthetic-token") {
        return jsonResponse(route, { detail: "CSRF required" }, 403);
      }
      hasSecondVersion = true;
      return jsonResponse(route, second, 201);
    }
    const downloads = new RegExp(`^${apiRoot}/reports/(${firstId}|${secondId})/download$`).exec(resource);
    if (downloads) {
      const version = downloads[1] === firstId ? first : second;
      const exportFormat = url.searchParams.get("export_format") ?? "pdf";
      if (exportFormat !== "pdf" && exportFormat !== "json") {
        return jsonResponse(route, { code: "invalid_export_format", detail: "Choose pdf or json." }, 400);
      }
      const extension = exportFormat === "pdf" ? "pdf" : "json";
      const body = exportFormat === "pdf"
        ? pdf
        : Buffer.from(JSON.stringify({
          export_schema_version: "1.0",
          postmortem_version: {
            id: version.id,
            incident_id: incidentId,
            number: version.version,
            created_at: version.created_at,
            content_sha256: version.content_sha256,
          },
          content: version.content,
        }));
      return route.fulfill({
        status: 200,
        contentType: exportFormat === "pdf" ? "application/pdf" : "application/json",
        headers: {
          "content-disposition": `attachment; filename="incidentforge-postmortem-v${version.version}-${version.id}.${extension}"`,
          "cache-control": "private, no-store",
          "x-content-type-options": "nosniff",
        },
        body,
      });
    }
    if (resource === `${apiRoot}/reports/${firstId}`) return jsonResponse(route, first);
    if (resource === `${apiRoot}/reports/${secondId}`) return jsonResponse(route, second);
    if (resource === `${apiRoot}`) {
      return jsonResponse(route, {
        id: incidentId,
        title: "Synthetic gateway timeout",
        description: "Browser acceptance fixture.",
        impact_notes: "",
        service_name: "gateway",
        environment: "development",
        timezone: "UTC",
        severity: "medium",
        status: "investigating",
        created_at: createdAt,
        updated_at: createdAt,
      });
    }
    return jsonResponse(route, { detail: `No synthetic fixture for ${resource}` }, 404);
  });
  return { getFinalization: () => finalizationPayload, getSecondCreated: () => hasSecondVersion };
}

test("frozen report displays AI vs human findings and downloads PDF/JSON", async ({ page }) => {
  await installSyntheticApi(page);
  await page.goto(`/incidents/${incidentId}/reports/${firstId}`);

  await expect(page.getByRole("heading", { name: "Synthetic gateway timeout", level: 1 })).toBeVisible();
  await expect(page.getByText("Version one: gateway timeout observed.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hypotheses and human decisions" })).toBeVisible();
  await expect(page.getByText("Human decision:")).toBeVisible();
  await expect(page.getByText("The cause remains unconfirmed.")).toBeVisible();
  await expect(page.getByText("Intermittent test checkouts failed.")).toBeVisible();

  const pdfLink = page.getByRole("link", { name: "Download PDF" });
  const jsonLink = page.getByRole("link", { name: "Download JSON" });
  await expect(pdfLink).toHaveAttribute("href", new RegExp(`download\\?export_format=pdf$`));
  await expect(jsonLink).toHaveAttribute("href", new RegExp(`download\\?export_format=json$`));

  // Chromium can cancel route-fulfilled downloads when the link uses the download attribute.
  // The mocked API already sends Content-Disposition: attachment, so remove the attribute
  // in this test only. The production component remains unchanged.
  await pdfLink.evaluate((element) => element.removeAttribute("download"));
  const [pdfDownload] = await Promise.all([page.waitForEvent("download"), pdfLink.click()]);
  const pdfBytes = readFileSync(await pdfDownload.path());
  expect(pdfBytes.subarray(0, 5).toString()).toBe("%PDF-");
  expect(pdfBytes.length).toBeGreaterThan(1000);
  expect(pdfDownload.suggestedFilename()).toBe(`incidentforge-postmortem-v1-${firstId}.pdf`);

  await jsonLink.evaluate((element) => element.removeAttribute("download"));
  const [jsonDownload] = await Promise.all([page.waitForEvent("download"), jsonLink.click()]);
  const exported = JSON.parse(readFileSync(await jsonDownload.path(), "utf-8"));
  expect(exported.postmortem_version.id).toBe(firstId);
  expect(exported.postmortem_version.number).toBe(1);
  expect(exported.content).toEqual(first.content);
  expect(jsonDownload.suggestedFilename()).toBe(`incidentforge-postmortem-v1-${firstId}.json`);

  await page.getByText("Source provenance and version metadata").click();
  await expect(page.getByText("synthetic-gateway.log")).toBeVisible();
});

test("version history and finalization navigate without changing version one", async ({ page }) => {
  const synthetic = await installSyntheticApi(page);
  await page.goto(`/incidents/${incidentId}/reports`);
  await expect(page.getByRole("heading", { name: "Postmortems" })).toBeVisible();
  await expect(page.getByText("Ready to finalize")).toBeVisible();
  await page.getByRole("button", { name: "Create report version" }).click();
  await expect(page.getByText("Version two: new human-review revision.")).toBeVisible();
  expect(synthetic.getSecondCreated()).toBe(true);
  expect(synthetic.getFinalization()).toEqual({
    investigation_id: investigationId,
    expected_review_revision: 2,
  });
  await page.getByRole("link", { name: "Postmortems" }).click();
  await expect(page.getByText("Version 2", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /Version 1/ }).click();
  await expect(page.getByText("Version one: gateway timeout observed.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Incident" })).toHaveAttribute("href", `/incidents/${incidentId}`);
  await expect(page.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
});

test("a rejected report detail displays an error but never offers exports", async ({ page }) => {
  await installSyntheticApi(page);
  await page.route(`**${apiRoot}/reports/${firstId}`, (route) => jsonResponse(
    route,
    { code: "report_integrity", detail: "This report version failed its integrity check." },
    409,
  ));
  await page.goto(`/incidents/${incidentId}/reports/${firstId}`);
  await expect(page.locator('main p[role="alert"]')).toContainText("failed its integrity check");
  await expect(page.getByRole("link", { name: "Download PDF" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Download JSON" })).toHaveCount(0);
});
