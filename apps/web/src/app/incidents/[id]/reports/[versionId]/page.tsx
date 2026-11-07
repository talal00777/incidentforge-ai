import { PostmortemDetail } from "@/components/m5/postmortem-detail";

export default async function PostmortemVersionPage({ params }: {
  params: Promise<{ id: string; versionId: string }>;
}) {
  const { id, versionId } = await params;
  return <PostmortemDetail incidentId={id} versionId={versionId} />;
}
