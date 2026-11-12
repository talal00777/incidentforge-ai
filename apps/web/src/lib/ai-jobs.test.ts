import { describe, expect, it } from "vitest";
import { isActiveJob, jobLabel, type AIJob } from "./ai-jobs";

const example = {
  job_id: "00000000-0000-4000-8000-000000000001",
  state: "queued",
  attempt_count: 0,
  cancel_requested: false,
  report_id: null,
  error: null,
  available_at: "2026-11-10T12:00:00Z",
  requested_at: "2026-11-10T12:00:00Z",
  started_at: null,
  completed_at: null,
} satisfies AIJob;

describe("investigation job state", () => {
  it("keeps queued, running, retrying and cancelling jobs active", () => {
    for (const state of ["queued", "running", "retry_wait", "cancelling"] as const) {
      expect(isActiveJob({ ...example, state })).toBe(true);
    }
    for (const state of ["cancelled", "succeeded", "failed"] as const) {
      expect(isActiveJob({ ...example, state })).toBe(false);
    }
  });

  it("maps states to concise status labels", () => {
    expect(jobLabel({ ...example, state: "retry_wait" })).toBe("Retry scheduled");
    expect(jobLabel({ ...example, state: "succeeded" })).toBe("Completed");
  });
});
