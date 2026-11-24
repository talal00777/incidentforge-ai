import { IncidentWorkspaceHeader } from "@/components/incident-workspace-header";
import { PostmortemDetail } from "@/components/m5/postmortem-detail";

export default async function PostmortemVersionPage({ params }: {
  params: Promise<{ id: string; versionId: string }>;
}) {
  const { id, versionId } = await params;
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <main id="main-content" className="workspace-content" tabIndex={-1}>
        <IncidentWorkspaceHeader incidentId={id} showTabs={false} />
        <PostmortemDetail incidentId={id} versionId={versionId} />
      </main>
    </>
  );
}
