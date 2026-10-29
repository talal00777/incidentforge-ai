import { EvidenceSnapshotsPanel } from "@/components/m4/evidence-snapshots-panel";

export default async function EvidenceSnapshotsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <EvidenceSnapshotsPanel incidentId={id} />;
}
