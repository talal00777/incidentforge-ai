/** Incident-scoped, direct-linkable report destinations. */
export function postmortemsPath(incidentId: string): string {
  return `/incidents/${encodeURIComponent(incidentId)}/reports`;
}

export function postmortemVersionPath(incidentId: string, versionId: string): string {
  return `${postmortemsPath(incidentId)}/${encodeURIComponent(versionId)}`;
}
