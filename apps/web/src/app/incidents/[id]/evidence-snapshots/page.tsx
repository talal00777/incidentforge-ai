import { AppShell } from "@/components/app-shell";
import { IncidentWorkspaceHeader } from "@/components/incident-workspace-header";
import { EvidenceSnapshotsPanel } from "@/components/m4/evidence-snapshots-panel";

export default async function EvidenceSnapshotsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <IncidentWorkspaceHeader incidentId={id} current="snapshots" />
        <EvidenceSnapshotsPanel incidentId={id} />
      </AppShell>
    </>
  );
}
