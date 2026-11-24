import { AppShell } from "@/components/app-shell";
import { IncidentWorkspaceHeader } from "@/components/incident-workspace-header";
import { IncidentDetail } from "@/components/m1/incident-detail";

export default async function IncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <IncidentWorkspaceHeader incidentId={id} current="overview" />
        <header className="page-heading">
          <div>
            <p className="page-overline">Incidents</p>
            <h1>Incident details</h1>
            <p className="page-subtitle">Update status and maintain an incident record.</p>
          </div>
        </header>
        <IncidentDetail />
      </AppShell>
    </>
  );
}
