import { describe, expect, it } from "vitest";
import { humanReviewPath, investigationPath, investigationReportPath } from "./investigation-routes";

describe("incident investigation routes", () => {
  it("opens an incident-scoped investigation setup page", () => {
    expect(investigationPath("incident-1")).toBe("/incidents/incident-1/investigations");
  });

  it("opens a saved AI investigation on its own page", () => {
    expect(investigationReportPath("incident-1", "report-2"))
      .toBe("/incidents/incident-1/investigations/report-2");
  });

  it("keeps the human review on a distinct page", () => {
    expect(humanReviewPath("incident-1", "report-2"))
      .toBe("/incidents/incident-1/investigations/report-2/review");
  });

  it("encodes dynamic path segments", () => {
    expect(humanReviewPath("incident/a", "report?b"))
      .toBe("/incidents/incident%2Fa/investigations/report%3Fb/review");
  });
});
