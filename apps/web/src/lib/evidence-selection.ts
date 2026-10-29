export const MAX_SELECTED_EVENTS = 60;

export function toggleEvidenceSelection(current: string[], id: string): string[] {
  if (current.includes(id)) return current.filter((value) => value !== id);
  if (current.length >= MAX_SELECTED_EVENTS) return current;
  return [...current, id];
}

export function selectionKey(ids: string[]): string {
  return [...ids].sort().join("|");
}

export function evidenceTime(value: string | null, zone: "utc" | "local"): string {
  if (!value) return "Time unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time unknown";
  const formatted = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit",
    minute: "2-digit", timeZone: zone === "utc" ? "UTC" : undefined,
    hour12: false,
  }).format(date);
  return `${formatted} ${zone === "utc" ? "UTC" : "local"}`;
}
