import { describe, expect, it } from "vitest";
import { timePositionPercent, timelineColumnWidth, timelineCountTicks } from "./analysis-timeline";

describe("incident timeline layout", () => {
  it("places sparse events according to their actual UTC occurrence times", () => {
    const first = "2026-10-27T08:00:00Z";
    const last = "2026-10-27T10:00:00Z";
    expect(timePositionPercent(first, first, last)).toBe(2);
    expect(timePositionPercent("2026-10-27T09:00:00Z", first, last)).toBe(50);
    expect(timePositionPercent(last, first, last)).toBe(98);
    expect(timePositionPercent("2026-10-27T08:10:00Z", first, last)).toBeCloseTo(10);
  });

  it("handles a single observed window without invalid geometry", () => {
    const start = "2026-10-27T08:00:00Z";
    expect(timePositionPercent(start, start, start)).toBe(50);
    expect(timePositionPercent("bad", start, start)).toBe(50);
  });

  it("shows integer count ticks and limits columns for crowded charts", () => {
    expect(timelineCountTicks(3)).toEqual([3, 2, 1, 0]);
    expect(timelineCountTicks(0)).toEqual([1, 0]);
    expect(timelineCountTicks(12)).toContain(0);
    expect(timelineColumnWidth([])).toBe(30);
    expect(timelineColumnWidth(Array.from({ length: 36 }, () => ({ start: "", total: 1, errors: 0 })))).toBe(16);
  });
});


describe("timeline axis bounds", () => {
  it("avoids infinite and nonfinite tick values", () => {
    for (const value of [Number.NaN, Number.POSITIVE_INFINITY, -100]) {
      expect(timelineCountTicks(value)).toEqual([1, 0]);
    }
  });
});
