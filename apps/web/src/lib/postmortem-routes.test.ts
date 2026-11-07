import { describe, expect, it } from "vitest";
import { postmortemsPath, postmortemVersionPath } from "./postmortem-routes";

describe("postmortem paths", () => {
  it("keeps every version under its incident", () => {
    expect(postmortemsPath("incident-id")).toBe("/incidents/incident-id/reports");
    expect(postmortemVersionPath("incident-id", "version-id")).toBe("/incidents/incident-id/reports/version-id");
  });
  it("encodes path segments", () => {
    expect(postmortemVersionPath("abc/def", "v 2")).toBe("/incidents/abc%2Fdef/reports/v%202");
  });
});
