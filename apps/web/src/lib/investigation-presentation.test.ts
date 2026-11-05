import { describe, expect, it } from "vitest";

import {
  distinctHypothesisChecks,
  hypothesisStatus,
  mergeSuggestedActions,
  readableInvestigationDate,
} from "./investigation-presentation";

describe("AI investigation report presentation", () => {
  it("labels hypothesis uncertainty without claiming proven causation", () => {
    expect(hypothesisStatus("supported_but_not_proven").label).toBe("Supported, not confirmed");
    expect(hypothesisStatus("plausible_unconfirmed").label).toBe("Plausible, unconfirmed");
    expect(hypothesisStatus("contradicted").label).toBe("Contradicted");
    expect(hypothesisStatus("unexpected").label).toBe("Unclassified");
  });

  it("uses explicit UTC/local labels without inventing missing times", () => {
    expect(readableInvestigationDate("2026-11-04T03:40:00Z", "utc")).toContain("04 Nov 2026");
    expect(readableInvestigationDate("2026-11-04T03:40:00Z", "utc")).toContain("UTC");
    expect(readableInvestigationDate("2026-11-04T03:40:00Z", "local")).toContain("local");
    expect(readableInvestigationDate(null, "utc")).toBe("Time unknown");
    expect(readableInvestigationDate("nonsense", "local")).toBe("Time unknown");
  });

  it("merges duplicate suggestions and preserves all citations", () => {
    const merged = mergeSuggestedActions([
      { action: "Review gateway logs.", safety: "review_only", rationale_event_ids: ["evt-1"] },
      { action: " review  gateway logs ", safety: "review_only", rationale_event_ids: ["evt-2", "evt-1"] },
      { action: "Check provider latency", safety: "review_only", rationale_event_ids: ["evt-3"] },
    ]);
    expect(merged).toHaveLength(2);
    expect(merged[0].rationale_event_ids).toEqual(["evt-1", "evt-2"]);
    expect(merged[1].action).toBe("Check provider latency");
  });

  it("keeps novel hypothesis checks but avoids repeating main suggestions", () => {
    expect(distinctHypothesisChecks(
      ["Review gateway logs", "Check trace IDs", " check trace  ids. "],
      ["Review gateway logs."],
    )).toEqual(["Check trace IDs"]);
  });
});
