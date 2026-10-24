export type ServiceState = "operational" | "degraded";

export interface ServiceHealth {
  state: ServiceState;
  checkedAt: string;
  reason: string | null;
}

export function normalizeReadiness(statusCode: number, payload: unknown): ServiceState {
  if (
    statusCode === 200 &&
    typeof payload === "object" &&
    payload !== null &&
    "status" in payload &&
    payload.status === "ready"
  ) {
    return "operational";
  }
  return "degraded";
}

export async function fetchServiceHealth(
  origin: string,
  fetcher: typeof fetch = fetch,
): Promise<ServiceHealth> {
  const checkedAt = new Date().toISOString();
  try {
    const response = await fetcher(`${origin}/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    const payload: unknown = await response.json();
    const state = normalizeReadiness(response.status, payload);
    return {
      state,
      checkedAt,
      reason: state === "operational" ? null : "One or more services are unavailable.",
    };
  } catch {
    return {
      state: "degraded",
      checkedAt,
      reason: "The API readiness endpoint could not be reached.",
    };
  }
}
