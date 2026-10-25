import { AppShell } from "@/components/app-shell";
import { IncidentsList } from "@/components/m1/incidents-list";

export default function IncidentsPage() {
  return <><a className="skip-link" href="#main-content">Skip to main content</a><AppShell><header className="page-heading"><div><p className="page-overline">Workspace</p><h1>Incidents</h1><p className="page-subtitle">Manage incident records and investigation status.</p></div></header><IncidentsList /></AppShell></>;
}
