import "./accessibility.css";
import { AppShell } from "@/components/app-shell";
import { ProductIcon } from "@/components/product-icon";
import { StatusPanel } from "@/components/status-panel";
import { fetchServiceHealth } from "@/lib/health";

export const dynamic = "force-dynamic";

const overviewMetrics = [
  { label: "Open incidents", description: "No incident data" },
  { label: "Investigations", description: "No investigation data" },
  { label: "Log sources", description: "No sources connected" },
];

export default async function HomePage() {
  const origin = process.env.INTERNAL_API_ORIGIN ?? "http://127.0.0.1:8000";
  const health = await fetchServiceHealth(origin);

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
      <span className="sr-only" id="unavailable-action-description">This action is not available yet.</span>
      <section className="page-heading">
        <div>
          <p className="page-overline">Operations</p>
          <h1>Incident overview</h1>
          <p className="page-subtitle">Monitor incidents, analyze evidence, and track investigations in one place.</p>
        </div>
        <button className="button button-primary" type="button" disabled aria-describedby="unavailable-action-description">
          <ProductIcon name="plus" size={18} /> New incident
        </button>
      </section>

      <section className="metric-grid" aria-label="Incident summary">
        {overviewMetrics.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <h2>{metric.label}</h2>
            <p className="metric-value"><span aria-hidden="true">—</span><span className="sr-only">Not available</span></p>
            <p className="metric-description">{metric.description}</p>
          </article>
        ))}
      </section>

      <section className="panel incidents-panel" aria-labelledby="incidents-heading">
        <div className="panel-header panel-header-with-actions">
          <div>
            <h2 id="incidents-heading">Incidents</h2>
            <p>View and manage reported service incidents.</p>
          </div>
          <button type="button" className="button button-outline" disabled aria-describedby="unavailable-action-description">All statuses</button>
        </div>
        <div className="table-scroll">
          <table className="incident-table">
            <caption className="sr-only">Incident records. There are currently no incidents to display.</caption>
            <thead><tr><th scope="col">Incident</th><th scope="col">Severity</th><th scope="col">Status</th><th scope="col">Last updated</th></tr></thead>
            <tbody>
              <tr>
                <td className="table-empty" colSpan={4}>
                  <div className="empty-state">
                    <span className="empty-icon"><ProductIcon name="inbox" size={26} /></span>
                    <strong>No incidents to display</strong>
                    <p>Incident records will appear here when available.</p>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div className="lower-grid">
        <section className="panel activity-panel" aria-labelledby="activity-heading">
          <div className="panel-header">
            <div><h2 id="activity-heading">Investigation activity</h2><p>Investigation events and trends.</p></div>
          </div>
          <div className="chart-placeholder" role="note">
            <ProductIcon name="activity" size={28} />
            <span>No activity data available</span>
          </div>
        </section>
        <StatusPanel health={health} />
      </div>

      <section className="quick-actions" aria-labelledby="actions-heading">
        <div className="section-title"><h2 id="actions-heading">Quick actions</h2></div>
        <div className="action-grid">
          <button type="button" className="action-card" disabled aria-describedby="unavailable-action-description">
            <ProductIcon name="upload" size={21} /><span>Upload logs</span>
          </button>
          <button type="button" className="action-card" disabled aria-describedby="unavailable-action-description">
            <ProductIcon name="investigations" size={21} /><span>Start investigation</span>
          </button>
          <button type="button" className="action-card" disabled aria-describedby="unavailable-action-description">
            <ProductIcon name="reports" size={21} /><span>Export report</span>
          </button>
        </div>
      </section>
      </AppShell>
    </>
  );
}
