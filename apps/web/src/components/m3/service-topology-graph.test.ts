import { describe, expect, it } from "vitest";
import { computeTopologyLayout } from "./service-topology-graph";

describe("service topology layout", () => {
  it("computes layered columns and error health classifications", () => {
    const layout = computeTopologyLayout(
      [
        { from_service: "api-gateway", to_service: "checkout-api", count: 14, event_ids: ["1"] },
        { from_service: "checkout-api", to_service: "postgres-primary", count: 9, event_ids: ["2"] },
      ],
      [
        { id: "1", severity: "INFO", service: "api-gateway" },
        { id: "2", severity: "ERROR", service: "checkout-api" },
        { id: "3", severity: "ERROR", service: "checkout-api" },
        { id: "4", severity: "INFO", service: "postgres-primary" },
        { id: "5", severity: "INFO", service: "postgres-primary" },
        { id: "6", severity: "INFO", service: "postgres-primary" },
        { id: "7", severity: "ERROR", service: "postgres-primary" },
      ],
    );

    const byId = new Map(layout.nodes.map((n) => [n.id, n]));
    expect(byId.get("api-gateway")!.x).toBeLessThan(byId.get("checkout-api")!.x);
    expect(byId.get("checkout-api")!.x).toBeLessThan(byId.get("postgres-primary")!.x);
    expect(byId.get("api-gateway")!.health).toBe("healthy");
    expect(byId.get("checkout-api")!.health).toBe("critical");
    expect(byId.get("postgres-primary")!.health).toBe("degraded");
  });

  it("handles cyclic transitions safely without infinite loops", () => {
    const layout = computeTopologyLayout(
      [
        { from_service: "svc-a", to_service: "svc-b", count: 3, event_ids: ["1"] },
        { from_service: "svc-b", to_service: "svc-a", count: 2, event_ids: ["2"] },
      ],
      [],
    );
    expect(layout.nodes).toHaveLength(2);
  });
});
