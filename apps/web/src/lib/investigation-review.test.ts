import { describe, expect, it } from "vitest";

import { canCompleteReview, updateHypothesis, type HumanReview } from "./investigation-review";

const initial: HumanReview = {
  revision: 1,
  status: "reviewed",
  hypotheses: [{ index: 0, decision: "reviewed", note: "Validated" }],
  impact_notes: "",
  remediation_notes: "",
  updated_at: null,
};

describe("human investigation review", () => {
  it("does not mark pending hypotheses complete", () => {
    expect(canCompleteReview([{ index: 0, decision: "needs_review", note: "" }])).toBe(false);
    expect(canCompleteReview(initial.hypotheses)).toBe(true);
  });

  it("reverts completion when a decision becomes pending, without mutating previous data", () => {
    const updated = updateHypothesis(initial, 0, { decision: "needs_review" });
    expect(updated.status).toBe("draft");
    expect(updated.hypotheses[0].decision).toBe("needs_review");
    expect(initial.hypotheses[0].decision).toBe("reviewed");
  });
});
