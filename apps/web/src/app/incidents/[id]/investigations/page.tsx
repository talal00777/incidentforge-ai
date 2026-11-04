import { InvestigationWorkspace } from "@/components/m4/investigation-workspace";

export default async function InvestigationsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <InvestigationWorkspace incidentId={id} />;
}
