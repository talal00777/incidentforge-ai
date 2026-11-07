export type PostmortemSummary = {
  id: string;
  version: number;
  investigation_id: string;
  review_revision_number: number;
  content_sha256: string;
  created_by_id: string;
  created_at: string;
};

export type SourceReference = {
  event_id: string;
  source_id: string;
  source_name: string;
  source_sha256: string;
  source_lines: [number, number];
  occurred_at: string | null;
  service: string;
};

type Fact = { statement: string; event_ids: string[] };
type Hypothesis = {
  title: string;
  status: string;
  supporting_event_ids: string[];
  contradicting_event_ids: string[];
  alternative_explanations: string[];
  further_checks: string[];
};
type SuggestedAction = { action: string; safety: string; rationale_event_ids: string[] };

export type PostmortemContent = {
  schema_version: string;
  incident: { id: string; title: string };
  ai: {
    investigation_id: string;
    created_at: string;
    provider: string;
    model_id: string;
    prompt_profile: string;
    prompt_version: string;
    response_schema_version: string;
    generation: { temperature: number; max_output_tokens: number };
    usage: { input_tokens: number | null; output_tokens: number | null };
    consent_accepted_at: string;
    evidence_snapshot: {
      id: string;
      sha256: string;
      selection_version: string;
      privacy_policy_version: string;
    };
    findings: {
      schema_version: string;
      incident_summary: string;
      observed_facts: Fact[];
      hypotheses: Hypothesis[];
      suggested_actions: SuggestedAction[];
      limitations: string[];
    };
  };
  human: {
    revision: number;
    status: "reviewed";
    author_id: string;
    reviewed_at: string;
    impact_notes: string;
    remediation_notes: string;
    hypotheses: { index: number; decision: string; note: string }[];
  };
  evidence_manifest: SourceReference[];
  timeline: { event_id: string; occurred_at: string | null; service: string; severity: string }[];
};

export type PostmortemVersion = PostmortemSummary & { content: PostmortemContent };

export type InvestigationSummary = { id: string; created_at: string; model_id: string };
export type SavedReview = { revision: number; status: "draft" | "reviewed"; hypotheses: { decision: string }[] };

export function isFinalizedReview(review: SavedReview | null): boolean {
  return Boolean(review && review.revision > 0 && review.status === "reviewed" &&
    review.hypotheses.every((item) => item.decision !== "needs_review"));
}
