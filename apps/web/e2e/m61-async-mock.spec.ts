import { expect, test, type Page, type Route } from "@playwright/test";

const incidentId = "22222222-2222-4222-8222-222222222222";
const snapshotId = "33333333-3333-4333-8333-333333333333";
const jobId = "44444444-4444-4444-8444-444444444444";
const reportId = "55555555-5555-4555-8555-555555555555";
const eventId = "66666666-6666-4666-8666-666666666666";
const createdAt = "2026-11-11T08:00:00Z";
const root = `/api/v1/incidents/${incidentId}`;
const workspace = `/incidents/${incidentId}/investigations`;

type State = "queued" | "running" | "retry_wait" | "cancelling" | "cancelled" | "succeeded" | "failed";
type Job = {
  job_id: string;
  state: State;
  attempt_count: number;
  cancel_requested: boolean;
  report_id: string | null;
  error: { code: string; retryable: boolean; message: string } | null;
  available_at: string;
  requested_at: string;
  started_at: string | null;
  completed_at: string | null;
};

function job(state: State, attemptCount = 0): Job {
  return {
    job_id: jobId,
    state,
    attempt_count: attemptCount,
    cancel_requested: state === "cancelling" || state === "cancelled",
    report_id: state === "succeeded" ? reportId : null,
    error: state === "failed"
      ? { code: "provider_error", retryable: false, message: "The AI provider is unavailable." }
      : state === "retry_wait"
        ? { code: "rate_limited", retryable: true, message: "The provider rate limit was reached." }
        : null,
    available_at: createdAt,
    requested_at: createdAt,
    started_at: state === "queued" ? null : createdAt,
    completed_at: ["cancelled", "succeeded", "failed"].includes(state) ? createdAt : null,
  };
}

const evidence = {
  id: snapshotId,
  sha256: "a".repeat(64),
  event_count: 1,
  payload_bytes: 300,
  created_at: createdAt,
  entries: [{
    event_id: eventId,
    source_id: "77777777-7777-4777-8777-777777777777",
    source_name: "gateway.log",
    source_lines: [18, 18],
    occurred_at: createdAt,
    severity: "ERROR",
    service: "gateway",
    message: "Upstream request timed out after 30 seconds.",
  }],
};

const report = {
  id: reportId,
  snapshot_id: snapshotId,
  provider: "openai",
  model_id: "gpt-4o-mini",
  temperature: 0.2,
  max_output_tokens: 2048,
  prompt_profile: "few_shot",
  created_at: createdAt,
  report: {
    schema_version: "1.0",
    incident_summary: "Gateway requests timed out.",
    observed_facts: [{ statement: "Upstream timeout recorded.", event_ids: [eventId] }],
    hypotheses: [{
      title: "Upstream service latency",
      status: "plausible_unconfirmed",
      supporting_event_ids: [eventId],
      contradicting_event_ids: [],
      alternative_explanations: [],
      further_checks: [],
    }],
    suggested_actions: [],
    limitations: ["Source logs do not establish the underlying cause."],
  },
};

function respond(route: Route, data: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
}

type Scenario = {
  initial?: Job;
  polls?: Job[];
  rejectSubmission?: boolean;
  cancelTo?: "cancelled" | "cancelling";
};

async function stubApi(page: Page, scenario: Scenario = {}) {
  let current = scenario.initial ?? null;
  let pollIndex = 0;
  let submissions = 0;
  let cancellations = 0;
  let submittedPayload: Record<string, unknown> | null = null;

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (path === "/api/v1/auth/me") {
      return respond(route, { id: "88888888-8888-4888-8888-888888888888", email: "reviewer@example.invalid", first_name: "A", last_name: "B" });
    }
    if (path === "/api/v1/auth/csrf") return respond(route, { csrf_token: "csrf-local" });
    if (path === "/api/v1/investigation/providers") {
      return respond(route, [{ name: "openai", models: ["gpt-4o-mini"], available: true }]);
    }
    if (path === `${root}/evidence/snapshots`) {
      const { entries: _entries, ...summary } = evidence;
      void _entries;
      return respond(route, [summary]);
    }
    if (path === `${root}/evidence/snapshots/${snapshotId}`) return respond(route, evidence);
    if (path === `${root}/investigations` && method === "GET") return respond(route, []);
    if (path === `${root}/ai-runs` && method === "GET") return respond(route, current ? [current] : []);
    if (path === `${root}/ai-runs` && method === "POST") {
      submissions += 1;
      submittedPayload = request.postDataJSON() as Record<string, unknown>;
      if (request.headers()["x-csrftoken"] !== "csrf-local") return respond(route, { detail: "CSRF validation failed." }, 403);
      if (scenario.rejectSubmission) return respond(route, { code: "investigation_active", detail: "An investigation is already running for this incident." }, 409);
      current = job("queued");
      return respond(route, current, 202);
    }
    if (path === `${root}/ai-runs/${jobId}` && method === "GET") {
      const replacement = scenario.polls?.[pollIndex];
      pollIndex += 1;
      if (replacement) current = replacement;
      return respond(route, current ?? job("queued"));
    }
    if (path === `${root}/ai-runs/${jobId}/cancel` && method === "POST") {
      cancellations += 1;
      if (request.headers()["x-csrftoken"] !== "csrf-local") return respond(route, { detail: "CSRF validation failed." }, 403);
      current = job(scenario.cancelTo ?? "cancelled", 1);
      return respond(route, current, 202);
    }
    if (path === `${root}/investigations/${reportId}` && method === "GET") return respond(route, report);
    return respond(route, { detail: "Not found." }, 404);
  });

  return {
    submissions: () => submissions,
    cancellations: () => cancellations,
    polls: () => pollIndex,
    payload: () => submittedPayload,
  };
}

async function startInvestigation(page: Page) {
  await page.goto(workspace);
  await expect(page.getByRole("heading", { name: "AI investigations", level: 1 })).toBeVisible();
  await expect(page.getByText("1 selected events")).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Generate investigation" }).click();
}

test("queued investigation progresses through retry and opens its saved report", async ({ page }) => {
  const api = await stubApi(page, { polls: [job("running", 1), job("retry_wait", 1), job("succeeded", 2)] });
  await startInvestigation(page);
  await expect(page.getByText("Waiting to start", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Investigation in progress" })).toBeDisabled();
  await expect(page.getByText("Investigating", { exact: true })).toBeVisible();
  await expect(page.getByText("Retry scheduled", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(`${workspace}/${reportId}`, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Investigation findings" })).toBeVisible();
  expect(api.submissions()).toBe(1);
  expect(api.polls()).toBeGreaterThanOrEqual(3);
  expect(api.payload()).toMatchObject({
    snapshot_id: snapshotId,
    provider: "openai",
    model_id: "gpt-4o-mini",
    prompt_profile: "decomposed_verified",
    transmission_consent: { accepted: true, snapshot_sha256: "a".repeat(64) },
  });
});

test("refresh restores an active job without another submission", async ({ page }) => {
  const api = await stubApi(page, { initial: job("queued"), polls: [job("queued"), job("running", 1)] });
  await page.goto(workspace);
  await expect(page.getByText("Waiting to start", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Waiting to start", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Investigation in progress" })).toBeDisabled();
  await expect(page.getByText("Investigating", { exact: true })).toBeVisible({ timeout: 10_000 });
  expect(api.submissions()).toBe(0);
});

test("a queued job can be cancelled without creating a report", async ({ page }) => {
  const api = await stubApi(page, { initial: job("queued"), cancelTo: "cancelled" });
  await page.goto(workspace);
  await expect(page.getByText("Waiting to start", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cancel investigation" }).click();
  await expect(page.getByRole("button", { name: "Cancel investigation" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Generate investigation" })).toBeVisible();
  expect(api.cancellations()).toBe(1);
  expect(api.submissions()).toBe(0);
  await expect(page).toHaveURL(workspace);
});

test("running cancellation hides the cancel action and retains job state", async ({ page }) => {
  const api = await stubApi(page, { initial: job("running", 1), cancelTo: "cancelling", polls: [job("cancelling", 1), job("cancelled", 1)] });
  await page.goto(workspace);
  await expect(page.getByText("Investigating", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cancel investigation" }).click();
  await expect(page.getByText("Cancelling", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel investigation" })).toHaveCount(0);
  await expect(page.locator('main p[role="alert"]')).toContainText("Investigation cancelled.", { timeout: 15_000 });
  expect(api.cancellations()).toBe(1);
});

test("a terminal provider failure is shown without opening a report", async ({ page }) => {
  const api = await stubApi(page, { polls: [job("failed", 1)] });
  await startInvestigation(page);
  await expect(page.locator('main p[role="alert"]')).toContainText("The AI provider is unavailable.", { timeout: 15_000 });
  await expect(page).toHaveURL(workspace);
  expect(api.submissions()).toBe(1);
});

test("submission conflicts do not create a local active job", async ({ page }) => {
  const api = await stubApi(page, { rejectSubmission: true });
  await startInvestigation(page);
  await expect(page.locator('main p[role="alert"]')).toContainText("An investigation is already running for this incident.");
  await expect(page.getByRole("button", { name: "Generate investigation" })).toBeVisible();
  expect(api.submissions()).toBe(1);
});
