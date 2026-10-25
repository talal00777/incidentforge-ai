export type Account = Readonly<{
  id: string;
  email: string;
  first_name: string;
  last_name: string;
}>;

export type Incident = Readonly<{
  id: string;
  title: string;
  description: string;
  service_name: string;
  environment: "production" | "staging" | "development" | "other";
  timezone: string;
  severity: "low" | "medium" | "high" | "critical";
  status: "open" | "investigating" | "resolved" | "archived";
  impact_notes: string;
  created_at: string;
  updated_at: string;
}>;

export type IncidentInput = Pick<
  Incident,
  "title" | "description" | "service_name" | "environment" | "timezone" | "severity"
>;

export type IncidentPage = Readonly<{
  count: number;
  next: string | null;
  previous: string | null;
  results: Incident[];
}>;

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function messageFromBody(body: unknown): string {
  if (!body || typeof body !== "object") return "The request could not be completed.";
  const record = body as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  for (const value of Object.values(record)) {
    if (typeof value === "string") return value;
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  }
  return "The request could not be completed.";
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(response.status, messageFromBody(body));
  return body as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  return parseResponse<T>(response);
}

export async function apiWrite<T>(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  payload?: unknown,
): Promise<T> {
  const csrf = await apiGet<{ csrf_token: string }>("auth/csrf");
  const response = await fetch(`/api/v1/${path}`, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": csrf.csrf_token,
    },
    ...(payload !== undefined ? { body: JSON.stringify(payload) } : {}),
  });
  return parseResponse<T>(response);
}

export function describeApiFailure(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Unable to connect to the application. Check your connection and try again.";
}
