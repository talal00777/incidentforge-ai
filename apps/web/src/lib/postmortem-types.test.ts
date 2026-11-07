import { describe, expect, it } from "vitest";
import { isFinalizedReview } from "./postmortem-types";

describe("postmortem finalization eligibility", () => {
  it("requires a saved, completed review", () => {
    expect(isFinalizedReview(null)).toBe(false);
    expect(isFinalizedReview({ revision: 0, status: "reviewed", hypotheses: [] })).toBe(false);
    expect(isFinalizedReview({ revision: 1, status: "draft", hypotheses: [{ decision: "reviewed" }] })).toBe(false);
    expect(isFinalizedReview({ revision: 1, status: "reviewed", hypotheses: [{ decision: "needs_review" }] })).toBe(false);
    expect(isFinalizedReview({ revision: 1, status: "reviewed", hypotheses: [{ decision: "accepted_as_working_hypothesis" }] })).toBe(true);
  });
});
