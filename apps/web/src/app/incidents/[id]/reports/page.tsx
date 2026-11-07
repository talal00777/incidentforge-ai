import { PostmortemWorkspace } from "@/components/m5/postmortem-workspace";

export default async function PostmortemsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PostmortemWorkspace incidentId={id} />;
}
