import Link from "next/link";
import { postmortemsPath } from "@/lib/postmortem-routes";
import { InvestigationWorkspace } from "@/components/m4/investigation-workspace";

export default async function InvestigationHumanReviewPage({ params }: {
  params: Promise<{ id: string; reportId: string }>;
}) {
  const { id, reportId } = await params;
  return <>
    <nav aria-label="Postmortem navigation" style={{ maxWidth: 1180, margin: "16px auto 0", padding: "0 24px", textAlign: "right" }}>
      <Link href={postmortemsPath(id)}>Postmortems</Link>
    </nav>
    <InvestigationWorkspace key={reportId} incidentId={id} reportId={reportId} view="human" />
  </>;
}
