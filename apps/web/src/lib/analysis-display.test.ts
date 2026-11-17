import { describe, expect, it } from "vitest";
import { CHART_PAGE_SIZE, chartPage, chartPages, eventTimeLabel, orderedTimeline, safePercent } from "./analysis-display";

describe("analysis presentation", () => {
  it("keeps chart pages bounded without silently dropping data", () => {
    const records = Array.from({ length: 80 }, (_, index) => index);
    expect(chartPages(records.length)).toBe(3);
    expect(chartPage(records, 0)).toHaveLength(CHART_PAGE_SIZE);
    expect(chartPage(records, 2)).toHaveLength(8);
    expect(chartPage(records, 100)).toEqual(records.slice(72));
    expect(chartPage([], 0)).toEqual([]);
  });
  it("avoids invalid or exaggerated bar values", () => {
    expect(safePercent(0, 0)).toBe(0);
    expect(safePercent(5, 10)).toBe(50);
    expect(safePercent(120, 100)).toBe(100);
    expect(safePercent(-1, 10)).toBe(0);
  });
  it("presents timezone aware time without exposing an ISO timestamp", () => {
    expect(eventTimeLabel("2026-10-27T08:10:00Z", "utc")).toContain("08:10");
    expect(eventTimeLabel("invalid", "utc")).toBe("Time unavailable");
  });
  it("sorts known timestamps and excludes malformed timestamps", () => {
    const ordered = orderedTimeline([
      { start: "2026-10-27T10:00:00Z", total: 1, errors: 0 },
      { start: "bad", total: 1, errors: 0 },
      { start: "2026-10-27T08:00:00Z", total: 2, errors: 1 },
    ]);
    expect(ordered.map((item) => item.total)).toEqual([2, 1]);
  });
});


describe("analysis pagination bounds", () => {
  it("handles nonfinite page input without dropping every chart item", () => {
    expect(chartPages(Number.NaN)).toBe(1);
    expect(chartPage([1, 2, 3], Number.NaN)).toEqual([1, 2, 3]);
    expect(chartPage([1, 2, 3], 1.5)).toEqual([1, 2, 3]);
  });
});
