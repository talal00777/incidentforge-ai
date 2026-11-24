import type { components } from "@/generated/api";

export type AnalysisBucket = components["schemas"]["TimelineBucket"];
export type AnalysisSeverity = components["schemas"]["CountBySeverity"];
export type AnalysisService = components["schemas"]["CountByService"];
export type AnalysisGroup = components["schemas"]["FingerprintGroup"];
export type IncidentAnalysis = components["schemas"]["Analysis"];

export const CHART_PAGE_SIZE = 36;

export function chartPages(length: number) {
  if (!Number.isFinite(length)) return 1;
  return Math.max(1, Math.ceil(Math.max(length, 0) / CHART_PAGE_SIZE));
}

export function chartPage<T>(values: T[], index: number) {
  const maxIndex = chartPages(values.length) - 1;
  const page = Number.isFinite(index) ? Math.min(Math.max(0, Math.trunc(index)), maxIndex) : 0;
  return values.slice(page * CHART_PAGE_SIZE, (page + 1) * CHART_PAGE_SIZE);
}

export function safePercent(value: number, max: number) {
  if (!Number.isFinite(value) || !Number.isFinite(max) || max <= 0) return 0;
  return Math.min(100, Math.max(0, (value / max) * 100));
}

export function eventTimeLabel(value: string, zone: "utc" | "local") {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    hourCycle: "h23", ...(zone === "utc" ? { timeZone: "UTC" } : {}),
  }).format(date);
}

export function orderedTimeline(buckets: AnalysisBucket[]) {
  return [...buckets].filter((item) => Number.isFinite(Date.parse(item.start)))
    .sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
}
