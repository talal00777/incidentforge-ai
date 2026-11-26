import { AppShell } from "@/components/app-shell";
import { IncidentWorkspaceHeader } from "@/components/incident-workspace-header";
import { WarRoomPanel } from "@/components/warroom/war-room-panel";

export default async function WarRoomPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <IncidentWorkspaceHeader incidentId={id} current="war-room" />
        <WarRoomPanel incidentId={id} />
      </AppShell>
    </>
  );
}
