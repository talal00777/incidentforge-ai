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
            <div><h2 id="activity-heading">Investigation workflow</h2><p>Structured steps from raw logs to immutable postmortem exports.</p></div>
          </div>
          <ol className="workflow-steps">
            <li className="workflow-step">
              <span className="workflow-step-num" aria-hidden="true">1</span>
              <div className="workflow-step-text"><strong>Upload &amp; normalize</strong><span>Ingest bounded log files with automatic redaction and line provenance.</span></div>
            </li>
            <li className="workflow-step">
              <span className="workflow-step-num" aria-hidden="true">2</span>
              <div className="workflow-step-text"><strong>Analyze &amp; correlate</strong><span>Inspect error buckets, fingerprint clusters, anomalies, and service transitions.</span></div>
            </li>
            <li className="workflow-step">
              <span className="workflow-step-num" aria-hidden="true">3</span>
              <div className="workflow-step-text"><strong>Consented AI synthesis</strong><span>Freeze a redacted snapshot and generate citation-checked hypotheses.</span></div>
            </li>
            <li className="workflow-step">
              <span className="workflow-step-num" aria-hidden="true">4</span>
              <div className="workflow-step-text"><strong>Review &amp; export</strong><span>Record human adjudication decisions and finalize PDF/JSON postmortems.</span></div>
            </li>
          </ol>
        </section>
        <StatusPanel health={health} />
      </div>

      <section className="quick-actions" aria-labelledby="actions-heading">
        <div className="section-title"><h2 id="actions-heading">Quick actions</h2></div>
        <div className="action-grid">
          <Link className="action-card" href="/incidents/new">
            <span className="action-card-icon" aria-hidden="true"><ProductIcon name="plus" size={20} /></span>
            <span className="action-card-body">
              <span className="action-card-title">Create incident</span>
              <span className="action-card-desc">Open a new investigation workspace</span>
            </span>
            <span className="action-card-arrow" aria-hidden="true">→</span>
          </Link>
          <Link className="action-card" href="/incidents">
            <span className="action-card-icon" aria-hidden="true"><ProductIcon name="investigations" size={20} /></span>
            <span className="action-card-body">
              <span className="action-card-title">Open incidents</span>
              <span className="action-card-desc">Browse active and resolved records</span>
            </span>
            <span className="action-card-arrow" aria-hidden="true">→</span>
          </Link>
          <Link className="action-card" href="/profile">
            <span className="action-card-icon" aria-hidden="true"><ProductIcon name="settings" size={20} /></span>
            <span className="action-card-body">
              <span className="action-card-title">Account profile</span>
              <span className="action-card-desc">Manage your workspace session</span>
            </span>
            <span className="action-card-arrow" aria-hidden="true">→</span>
          </Link>
        </div>
      </section>
      </AppShell>
    </>
  );
}
