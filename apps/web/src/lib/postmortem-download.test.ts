import { describe, expect, it } from "vitest";

import { postmortemDownloadPath } from "./postmortem-routes";

describe("postmortem download routes", () => {
  it("keeps PDF and JSON scoped to the immutable version", () => {
    expect(postmortemDownloadPath("incident-1", "version-2", "pdf")).toBe(
      "/api/v1/incidents/incident-1/reports/version-2/download?export_format=pdf",
    );
    expect(postmortemDownloadPath("incident-1", "version-2", "json")).toBe(
      "/api/v1/incidents/incident-1/reports/version-2/download?export_format=json",
    );
  });

  it("encodes route parameters", () => {
    expect(postmortemDownloadPath("a/b", "v?1", "pdf")).toContain(
      "/a%2Fb/reports/v%3F1/download?export_format=pdf",
    );
  });
});
