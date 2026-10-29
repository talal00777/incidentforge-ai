import { RelationshipsPanel } from "@/components/m3/relationships-panel";

export default async function RelationshipsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RelationshipsPanel incidentId={id} />;
}
