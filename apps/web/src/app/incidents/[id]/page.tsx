import { AppShell } from "@/components/app-shell";
import { IncidentDetail } from "@/components/m1/incident-detail";

export default function IncidentPage() {
  return <><a className="skip-link" href="#main-content">Skip to main content</a><AppShell><header className="page-heading"><div><p className="page-overline">Incidents</p><h1>Incident details</h1><p className="page-subtitle">Update status and maintain an incident record.</p></div></header><IncidentDetail /></AppShell></>;
}
