import { AnalysisPanel } from "@/components/m3/analysis-panel";

export default async function IncidentAnalysisPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <main><AnalysisPanel incidentId={id} /></main>;
}
