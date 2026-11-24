import { apiGet, apiWrite, type Incident } from "./api-client";

export type DashboardCounts = Readonly<{
  total: number;
  open: number;
  investigating: number;
  resolved: number;
  archived: number;
  critical_open: number;
  high_open: number;
}>;

export type DashboardSeverityRow = Readonly<{
  severity: "critical" | "high" | "medium" | "low" | string;
  count: number;
  open_count: number;
}>;

export type DashboardTelemetryTotals = Readonly<{
  total_sources: number;
  total_events: number;
  total_error_events: number;
  total_snapshots: number;
  total_investigations: number;
  total_postmortems: number;
}>;

export type DashboardServiceHealth = Readonly<{
  service: string;
  incident_count: number;
  event_count: number;
  error_events: number;
}>;

export type DashboardRecentIncident = Readonly<{
  id: string;
  title: string;
  service_name: string;
  environment: string;
  severity: "low" | "medium" | "high" | "critical";
  status: "open" | "investigating" | "resolved" | "archived";
  created_at: string;
  updated_at: string;
  source_count: number;
  event_count: number;
  error_count: number;
  investigation_count: number;
  postmortem_count: number;
}>;

export type DashboardActivity = Readonly<{
  id: string;
  kind: string;
  summary: string;
  incident_id: string;
  incident_title: string;
  occurred_at: string;
}>;

export type DashboardSummary = Readonly<{
  counts: DashboardCounts;
  severity_breakdown: DashboardSeverityRow[];
  telemetry_totals: DashboardTelemetryTotals;
  mttr_minutes: number | null;
  service_health: DashboardServiceHealth[];
  recent_incidents: DashboardRecentIncident[];
  recent_activity: DashboardActivity[];
}>;

export type DemoScenario = Readonly<{
  id: string;
  title: string;
  subtitle: string;
  service_name: string;
  environment: string;
  severity: "low" | "medium" | "high" | "critical";
  services: string[];
  expected_signals: string[];
}>;

export type DemoSeedResult = Readonly<{
  scenario_id: string;
  incident: Incident;
  sources_created: number;
  events_created: number;
  snapshot_id: string;
}>;

export function fetchDashboardSummary(): Promise<DashboardSummary> {
  return apiGet<DashboardSummary>("dashboard/summary");
}

export function fetchDemoScenarios(): Promise<DemoScenario[]> {
  return apiGet<DemoScenario[]>("demo/scenarios");
}

export function seedDemoScenario(scenarioId: string): Promise<DemoSeedResult> {
  return apiWrite<DemoSeedResult>("demo/scenarios", "POST", { scenario_id: scenarioId });
}

export function formatDurationMinutes(minutes: number | null): string {
  if (minutes === null || !Number.isFinite(minutes)) return "—";
  if (minutes < 1) return "<1m";
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = Math.floor(minutes / 60);
  const rem = Math.round(minutes % 60);
  if (hours < 24) return rem > 0 ? `${hours}h ${rem}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return remHours > 0 ? `${days}d ${remHours}h` : `${days}d`;
}

export function formatErrorRate(errors: number, total: number): string {
  if (!Number.isFinite(total) || total <= 0) return "0.0%";
  const pct = (Math.max(0, errors) / total) * 100;
  return `${pct.toFixed(pct >= 10 ? 1 : 1)}%`;
}

export function formatRelativeAge(iso: string, nowMs: number = Date.now()): string {
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return "—";
  const diffSec = Math.max(0, Math.floor((nowMs - parsed) / 1000));
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return new Date(parsed).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
}
