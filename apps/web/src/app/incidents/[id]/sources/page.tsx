import { AppShell } from "@/components/app-shell";
import { EvidencePanel } from "@/components/m2/evidence-panel";

export default async function SourcesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <header className="page-heading">
          <div>
            <p className="page-overline">Incidents</p>
            <h1>Incident evidence</h1>
            <p className="page-subtitle">Upload and inspect evidence associated with this incident.</p>
          </div>
        </header>
        <EvidencePanel incidentId={id} />
      </AppShell>
    </>
  );
}
