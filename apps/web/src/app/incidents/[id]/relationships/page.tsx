import { AppShell } from "@/components/app-shell";
import { IncidentWorkspaceHeader } from "@/components/incident-workspace-header";
import { RelationshipsPanel } from "@/components/m3/relationships-panel";

export default async function RelationshipsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <IncidentWorkspaceHeader incidentId={id} current="relationships" />
        <RelationshipsPanel incidentId={id} />
      </AppShell>
    </>
  );
}
