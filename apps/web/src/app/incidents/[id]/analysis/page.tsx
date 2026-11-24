import { AppShell } from "@/components/app-shell";
import { IncidentWorkspaceHeader } from "@/components/incident-workspace-header";
import { AnalysisPanel } from "@/components/m3/analysis-panel";

export default async function IncidentAnalysisPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <IncidentWorkspaceHeader incidentId={id} current="analysis" />
        <AnalysisPanel incidentId={id} />
      </AppShell>
    </>
  );
}
