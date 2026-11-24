import { describe, expect, it } from "vitest";
import { formatDurationMinutes, formatErrorRate, formatRelativeAge } from "./dashboard-api";

describe("dashboard formatting helpers", () => {
  it("formats MTTR durations cleanly across minute, hour, and day scales", () => {
    expect(formatDurationMinutes(null)).toBe("—");
    expect(formatDurationMinutes(0.4)).toBe("<1m");
    expect(formatDurationMinutes(42.2)).toBe("42m");
    expect(formatDurationMinutes(95)).toBe("1h 35m");
    expect(formatDurationMinutes(120)).toBe("2h");
    expect(formatDurationMinutes(1560)).toBe("1d 2h");
  });

  it("formats error rate safely including zero-event baselines", () => {
    expect(formatErrorRate(0, 0)).toBe("0.0%");
    expect(formatErrorRate(25, 200)).toBe("12.5%");
    expect(formatErrorRate(1, 500)).toBe("0.2%");
  });

  it("formats relative timestamps deterministically", () => {
    const now = Date.parse("2026-11-24T12:00:00Z");
    expect(formatRelativeAge("2026-11-24T11:59:30Z", now)).toBe("just now");
    expect(formatRelativeAge("2026-11-24T11:42:00Z", now)).toBe("18m ago");
    expect(formatRelativeAge("2026-11-24T08:00:00Z", now)).toBe("4h ago");
    expect(formatRelativeAge("2026-11-21T12:00:00Z", now)).toBe("3d ago");
    expect(formatRelativeAge("invalid", now)).toBe("—");
  });
});
