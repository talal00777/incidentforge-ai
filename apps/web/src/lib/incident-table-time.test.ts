import { describe, expect, it } from "vitest";
import { incidentUpdatedAt } from "./incident-table-time";

describe("incident table timestamps", () => {
  it("preserves a machine-readable UTC instant", () => {
    expect(incidentUpdatedAt("2026-11-17T21:30:00+01:00")).toEqual({
      label: "17 Nov 2026, 20:30 UTC", iso: "2026-11-17T20:30:00.000Z",
    });
  });
  it("does not display an invalid date", () => {
    expect(incidentUpdatedAt("not-a-time")).toBeNull();
  });
});
