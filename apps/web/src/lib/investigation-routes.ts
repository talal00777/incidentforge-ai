/** Canonical incident-scoped investigation destinations. */
export function investigationPath(incidentId: string): string {
  return `/incidents/${encodeURIComponent(incidentId)}/investigations`;
}

export function investigationReportPath(incidentId: string, reportId: string): string {
  return `${investigationPath(incidentId)}/${encodeURIComponent(reportId)}`;
}

export function humanReviewPath(incidentId: string, reportId: string): string {
  return `${investigationReportPath(incidentId, reportId)}/review`;
}
