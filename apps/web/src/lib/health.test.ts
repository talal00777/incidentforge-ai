import { describe, expect, it, vi } from "vitest";
import { fetchServiceHealth, normalizeReadiness } from "./health";

describe("normalizeReadiness", () => {
  it("accepts a successful readiness response", () => {
    expect(normalizeReadiness(200, { status: "ready" })).toBe("operational");
  });

  it("rejects unavailable and malformed responses", () => {
    expect(normalizeReadiness(503, { status: "ready" })).toBe("degraded");
    expect(normalizeReadiness(200, { status: "alive" })).toBe("degraded");
    expect(normalizeReadiness(200, null)).toBe("degraded");
  });
});

describe("fetchServiceHealth", () => {
  it("returns a degraded state when the backend cannot be reached", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("connection refused"));
    const result = await fetchServiceHealth("http://localhost:8000", fetcher);
    expect(result.state).toBe("degraded");
    expect(result.reason).toMatch(/could not be reached/i);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("returns operational for a healthy API", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ status: "ready" }),
    });
    const result = await fetchServiceHealth("http://localhost:8000", fetcher);
    expect(result).toMatchObject({ state: "operational", reason: null });
  });
});
