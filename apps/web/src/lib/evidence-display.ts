export type DisplayTimezone = "utc" | "local";

export type EvidenceEvent = {
  id: string;
  source_id: string;
  line_start: number | null;
  line_end?: number | null;
  occurred_at: string | null;
  timestamp_quality: string;
  severity: string;
  service?: string;
  message: string;
};

export type EventSort = "latest" | "earliest" | "source";

export function describeTime(value: string | null, quality: string, zone: DisplayTimezone) {
  if (!value) {
    return {
      date: "Time unavailable",
      clock: quality === "unknown_timezone" ? "Timezone not supplied" : "No valid event time",
      valid: false,
    };
  }
  const time = new Date(value);
  if (!Number.isFinite(time.getTime())) {
    return { date: "Time unavailable", clock: "Invalid timestamp", valid: false };
  }
  const options: Intl.DateTimeFormatOptions = {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
    ...(zone === "utc" ? { timeZone: "UTC" } : {}),
  };
  const pieces = new Intl.DateTimeFormat("en-GB", options).formatToParts(time);
  const part = (name: string) => pieces.find((item) => item.type === name)?.value ?? "";
  return {
    date: `${part("day")} ${part("month")} ${part("year")}`,
    clock: `${part("hour")}:${part("minute")}:${part("second")} ${zone === "utc" ? "UTC" : "local"}`,
    valid: true,
  };
}

export function formatLineRange(start: number | null, end?: number | null) {
  if (start === null || start === undefined || !Number.isSafeInteger(start) || start < 1) return "Line unavailable";
  if (end && Number.isSafeInteger(end) && end > start) return `Lines ${start}–${end}`;
  return `Line ${start}`;
}

export function selectVisibleEvents(
  records: EvidenceEvent[],
  options: { query: string; severity: string; sourceId: string; sort: EventSort },
): EvidenceEvent[] {
  const terms = options.query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const filtered = records.filter((record) => {
    if (options.severity && record.severity.toUpperCase() !== options.severity) return false;
    if (options.sourceId && record.source_id !== options.sourceId) return false;
    if (!terms.length) return true;
    const searchable = `${record.message} ${record.service ?? ""} ${record.severity} ${record.source_id}`.toLocaleLowerCase();
    return terms.every((term) => searchable.includes(term));
  });
  if (options.sort === "source") {
    return [...filtered].sort((a, b) =>
      a.source_id.localeCompare(b.source_id) ||
      (a.line_start ?? Number.MAX_SAFE_INTEGER) - (b.line_start ?? Number.MAX_SAFE_INTEGER) ||
      a.id.localeCompare(b.id),
    );
  }
  return [...filtered].sort((a, b) => {
    const aTime = a.occurred_at ? Date.parse(a.occurred_at) : Number.NaN;
    const bTime = b.occurred_at ? Date.parse(b.occurred_at) : Number.NaN;
    const aValid = Number.isFinite(aTime);
    const bValid = Number.isFinite(bTime);
    if (!aValid && !bValid) return 0;
    if (!aValid) return 1;
    if (!bValid) return -1;
    return options.sort === "latest" ? bTime - aTime : aTime - bTime;
  });
}

export function isErrorSeverity(value: string) {
  return ["ERROR", "FATAL", "CRITICAL"].includes(value.toUpperCase());
}
