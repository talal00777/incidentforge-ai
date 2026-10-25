import { AppShell } from "@/components/app-shell";
import { CreateIncident } from "@/components/m1/create-incident";

export default function NewIncidentPage() {
  return <><a className="skip-link" href="#main-content">Skip to main content</a><AppShell><header className="page-heading"><div><p className="page-overline">Incidents</p><h1>New incident</h1><p className="page-subtitle">Record an operational incident.</p></div></header><CreateIncident /></AppShell></>;
}
