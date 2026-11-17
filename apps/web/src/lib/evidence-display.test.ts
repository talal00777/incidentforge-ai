import { describe, expect, it } from "vitest";
import { describeTime, formatLineRange, selectVisibleEvents, type EvidenceEvent } from "./evidence-display";

const events: EvidenceEvent[] = [
  { id: "a", source_id: "one", line_start: 1, line_end: 4, occurred_at: "2026-10-27T08:10:00Z", timestamp_quality: "explicit", severity: "ERROR", message: "database timeout" },
  { id: "b", source_id: "two", line_start: null, occurred_at: null, timestamp_quality: "unknown_timezone", severity: "WARN", message: "retrying" },
  { id: "c", source_id: "one", line_start: 7, occurred_at: "2026-10-27T08:00:00Z", timestamp_quality: "explicit", severity: "INFO", message: "service started" },
];

describe("evidence presentation", () => {
  it("formats UTC dates with a readable time and explicit timezone", () => {
    expect(describeTime("2026-10-27T09:00:00+01:00", "explicit", "utc")).toEqual({
      date: "27 Oct 2026", clock: "08:00:00 UTC", valid: true,
    });
  });
  it("explains timestamps without timezone instead of inventing one", () => {
    expect(describeTime(null, "unknown_timezone", "utc").clock).toBe("Timezone not supplied");
  });
  it("preserves source line ranges", () => {
    expect(formatLineRange(1, 4)).toBe("Lines 1–4");
    expect(formatLineRange(null)).toBe("Line unavailable");
  });
  it("sorts known times with unknown times last", () => {
    const rows = selectVisibleEvents(events, { query: "", severity: "", sourceId: "", sort: "latest" });
    expect(rows.map((row) => row.id)).toEqual(["a", "c", "b"]);
  });
  it("filters by severity, file source and message", () => {
    const rows = selectVisibleEvents(events, { query: "TIMEOUT", severity: "ERROR", sourceId: "one", sort: "source" });
    expect(rows.map((row) => row.id)).toEqual(["a"]);
  });
  it("never mutates the fetched event list", () => {
    selectVisibleEvents(events, { query: "", severity: "", sourceId: "", sort: "earliest" });
    expect(events.map((row) => row.id)).toEqual(["a", "b", "c"]);
  });
});


describe("evidence search and provenance ordering", () => {
  it("matches terms across message and source without depending on term order", () => {
    expect(selectVisibleEvents(events, { query: "one timeout", severity: "", sourceId: "", sort: "latest" }).map((row) => row.id)).toEqual(["a"]);
    expect(selectVisibleEvents(events, { query: "timeout one", severity: "", sourceId: "", sort: "latest" }).map((row) => row.id)).toEqual(["a"]);
  });
  it("orders sources by line number and returns a fresh array", () => {
    const original = [...events];
    expect(selectVisibleEvents(events, { query: "", severity: "", sourceId: "", sort: "source" }).map((row) => row.id)).toEqual(["a", "c", "b"]);
    expect(events).toEqual(original);
    expect(formatLineRange(Number.NaN)).toBe("Line unavailable");
  });
});
