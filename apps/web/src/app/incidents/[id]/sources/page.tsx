import { AppShell } from "@/components/app-shell";
import { IncidentWorkspaceHeader } from "@/components/incident-workspace-header";
import { EvidencePanel } from "@/components/m2/evidence-panel";

export default async function SourcesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <IncidentWorkspaceHeader incidentId={id} current="sources" />
        <EvidencePanel incidentId={id} />
      </AppShell>
    </>
  );
}
