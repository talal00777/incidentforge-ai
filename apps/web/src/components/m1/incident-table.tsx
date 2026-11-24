import Link from "next/link";
import type { Incident } from "@/lib/api-client";
import { incidentUpdatedAt } from "@/lib/incident-table-time";

export function IncidentTable({ incidents }: { incidents: readonly Incident[] }) {
  if (incidents.length === 0) return <p className="m1-empty">No matching incidents.</p>;
  return <div className="table-scroll">
    <table className="incident-table m1-table">
      <caption className="sr-only">Your incidents</caption>
      <thead><tr><th scope="col">Incident</th><th scope="col">Service</th><th scope="col">Severity</th><th scope="col">Status</th><th scope="col">Updated</th></tr></thead>
      <tbody>{incidents.map((incident) => {
        const updated = incidentUpdatedAt(incident.updated_at);
        return <tr key={incident.id}>
        <td><Link className="m1-table-link" href={`/incidents/${incident.id}`}>{incident.title}</Link></td>
        <td>{incident.service_name || "—"}</td>
        <td><span className={`if-badge if-badge-${incident.severity}`}>{incident.severity}</span></td>
        <td><span className={`if-badge if-badge-${incident.status}`}>{incident.status}</span></td>
        <td className="m1-time">{updated ? <time dateTime={updated.iso} title={updated.label}>{updated.label}</time> : "Time unavailable"}</td>
      </tr>;
      })}</tbody>
    </table>
  </div>;
}
