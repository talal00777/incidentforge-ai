export function incidentUpdatedAt(value: string): { label: string; iso: string } | null {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  return {
    label: `${new Intl.DateTimeFormat("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC",
    }).format(date)} UTC`,
    iso: date.toISOString(),
  };
}
