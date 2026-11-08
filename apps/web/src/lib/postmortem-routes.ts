/** Incident-scoped, direct-linkable report destinations. */
export function postmortemsPath(incidentId: string): string {
  return `/incidents/${encodeURIComponent(incidentId)}/reports`;
}

export function postmortemVersionPath(incidentId: string, versionId: string): string {
  return `${postmortemsPath(incidentId)}/${encodeURIComponent(versionId)}`;
}

export type PostmortemExportFormat = "pdf" | "json";

export function postmortemDownloadPath(
  incidentId: string,
  versionId: string,
  format: PostmortemExportFormat,
): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/reports/${encodeURIComponent(versionId)}/download?export_format=${format}`;
}
