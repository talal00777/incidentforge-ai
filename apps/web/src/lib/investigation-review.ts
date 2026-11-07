export type HumanReviewDecision =
  | "needs_review"
  | "reviewed"
  | "accepted_as_working_hypothesis"
  | "rejected";

export type HypothesisReview = { index: number; decision: HumanReviewDecision; note: string };

export type HumanReview = {
  revision: number;
  status: "draft" | "reviewed";
  hypotheses: HypothesisReview[];
  impact_notes: string;
  remediation_notes: string;
  updated_at: string | null;
};

export function canCompleteReview(hypotheses: HypothesisReview[]): boolean {
  return hypotheses.every((item) => item.decision !== "needs_review");
}

export function updateHypothesis(
  review: HumanReview,
  index: number,
  change: Partial<Pick<HypothesisReview, "decision" | "note">>,
): HumanReview {
  const hypotheses = review.hypotheses.map((item) => (
    item.index === index ? { ...item, ...change } : item
  ));
  return {
    ...review,
    hypotheses,
    status: review.status === "reviewed" && !canCompleteReview(hypotheses) ? "draft" : review.status,
  };
}
