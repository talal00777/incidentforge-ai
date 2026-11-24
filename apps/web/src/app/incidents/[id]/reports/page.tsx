import { AppShell } from "@/components/app-shell";
import { IncidentWorkspaceHeader } from "@/components/incident-workspace-header";
import { PostmortemWorkspace } from "@/components/m5/postmortem-workspace";

export default async function PostmortemsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <IncidentWorkspaceHeader incidentId={id} current="reports" />
        <PostmortemWorkspace incidentId={id} />
      </AppShell>
    </>
  );
}
