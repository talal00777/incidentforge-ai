import { describe, expect, it } from "vitest";

import { evidenceTime, MAX_SELECTED_EVENTS, selectionKey, toggleEvidenceSelection } from "./evidence-selection";

describe("evidence selection", () => {
  it("toggles without duplicates and enforces the selection limit", () => {
    expect(toggleEvidenceSelection(["a"], "a")).toEqual([]);
    expect(toggleEvidenceSelection(["a"], "b")).toEqual(["a", "b"]);
    const full = Array.from({ length: MAX_SELECTED_EVENTS }, (_, index) => String(index));
    expect(toggleEvidenceSelection(full, "new")).toEqual(full);
  });
  it("uses a selection-independent key", () => {
    expect(selectionKey(["b", "a"])).toEqual(selectionKey(["a", "b"]));
  });
  it("labels uncertain times and UTC explicitly", () => {
    expect(evidenceTime(null, "utc")).toBe("Time unknown");
    expect(evidenceTime("bad", "utc")).toBe("Time unknown");
    expect(evidenceTime("2026-10-27T08:00:00Z", "utc")).toContain("UTC");
  });
});
