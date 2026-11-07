import { InvestigationWorkspace } from "@/components/m4/investigation-workspace";

export default async function InvestigationReportPage({ params }: {
  params: Promise<{ id: string; reportId: string }>;
}) {
  const { id, reportId } = await params;
  return <InvestigationWorkspace key={reportId} incidentId={id} reportId={reportId} view="ai" />;
}
