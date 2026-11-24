import { AppShell } from "@/components/app-shell";
import { IncidentWorkspaceHeader } from "@/components/incident-workspace-header";
import { InvestigationWorkspace } from "@/components/m4/investigation-workspace";

export default async function InvestigationsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <IncidentWorkspaceHeader incidentId={id} current="investigations" />
        <InvestigationWorkspace incidentId={id} />
      </AppShell>
    </>
  );
}
