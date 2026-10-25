import Link from "next/link";
import { IncidentOverview } from "@/components/m1/incident-overview";
import "./accessibility.css";
import { AppShell } from "@/components/app-shell";
import { ProductIcon } from "@/components/product-icon";
import { StatusPanel } from "@/components/status-panel";
import { fetchServiceHealth } from "@/lib/health";

export const dynamic = "force-dynamic";

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
        <Link className="button button-primary" href="/incidents/new"><ProductIcon name="plus" size={18} /> New incident</Link>
      </section>

      <IncidentOverview />

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
