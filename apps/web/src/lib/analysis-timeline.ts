import type { AnalysisBucket } from "@/lib/analysis-display";

export function timePositionPercent(start: string, first: string, last: string): number {
  const begin = Date.parse(first);
  const end = Date.parse(last);
  const current = Date.parse(start);
  if (![begin, end, current].every(Number.isFinite) || end <= begin) return 50;
  return Math.max(2, Math.min(98, 2 + ((current - begin) / (end - begin)) * 96));
}

export function timelineCountTicks(maximum: number): number[] {
  const top = Math.max(1, Math.ceil(maximum));
  if (top <= 4) return Array.from({ length: top + 1 }, (_, index) => top - index);
  return [...new Set([top, Math.round(top * 0.75), Math.round(top * 0.5), Math.round(top * 0.25), 0])];
}

export function timelineColumnWidth(buckets: AnalysisBucket[]): number {
  return Math.max(10, Math.min(30, Math.floor(600 / Math.max(1, buckets.length))));
}
