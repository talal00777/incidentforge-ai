"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAccount } from "@/components/m1/use-account";
import { ApiError, describeApiFailure } from "@/lib/api-client";
import {
  fetchDashboardSummary,
  fetchDemoScenarios,
  formatDurationMinutes,
  formatErrorRate,
  formatRelativeAge,
  seedDemoScenario,
  type DashboardSummary,
  type DemoScenario,
} from "@/lib/dashboard-api";
import type { ServiceHealth } from "@/lib/health";

type StatusFilter = "all" | "active" | "resolved";
type FeedTab = "incidents" | "activity";

const CAPABILITIES = [
  {
    step: "01",
    title: "Log ingestion & redaction",
    desc: "Parse JSON, syslog, and tracebacks with automatic secret scrubbing and line provenance.",
  },
  {
    step: "02",
    title: "Burst detection & topology",
    desc: "Surface anomaly spikes, recurring error patterns, and cross-service trace graphs.",
  },
  {
    step: "03",
    title: "Evidence-grounded AI",
    desc: "Freeze redacted snapshots and synthesize citation-checked hypotheses on demand.",
  },
  {
    step: "04",
    title: "Human review & postmortems",
    desc: "Record operator decisions separately from AI output and export versioned PDF/JSON reports.",
  },
] as const;

function activityDotClass(kind: string): string {
  if (kind.includes("source") || kind.includes("upload")) return "dash-activity-dot kind-source";
  if (kind.includes("investigation") || kind.includes("ai")) return "dash-activity-dot kind-ai";
  if (kind.includes("postmortem") || kind.includes("report")) return "dash-activity-dot kind-report";
  return "dash-activity-dot";
}

export function OperationalDashboard({ health }: { health: ServiceHealth }) {
  const account = useAccount();
  const router = useRouter();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [scenarios, setScenarios] = useState<DemoScenario[]>([]);
  const [feedTab, setFeedTab] = useState<FeedTab>("incidents");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [demoModalOpen, setDemoModalOpen] = useState(false);
  const [error, setError] = useState("");
  const [seedingId, setSeedingId] = useState<string | null>(null);
  const [seedError, setSeedError] = useState("");

  useEffect(() => {
    if (account.state !== "signed-in") return;
    let active = true;
    Promise.all([
      fetchDashboardSummary(),
      fetchDemoScenarios().catch(() => [] as DemoScenario[]),
    ])
      .then(([dashboardData, scenarioList]) => {
        if (!active) return;
        setSummary(dashboardData);
        setScenarios(scenarioList);
        setError("");
      })
      .catch((failure: unknown) => {
        if (!active) return;
        setError(failure instanceof ApiError ? failure.message : describeApiFailure(failure));
      });
    return () => {
      active = false;
    };
  }, [account.state]);

  useEffect(() => {
    if (!demoModalOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setDemoModalOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [demoModalOpen]);

  const visibleIncidents = useMemo(() => {
    const items = summary?.recent_incidents ?? [];
    if (statusFilter === "active") {
      return items.filter((item) => item.status === "open" || item.status === "investigating");
    }
    if (statusFilter === "resolved") {
      return items.filter((item) => item.status === "resolved" || item.status === "archived");
    }
    return items;
  }, [statusFilter, summary]);

  async function launchDemo(scenarioId: string) {
    if (seedingId) return;
    setSeedingId(scenarioId);
    setSeedError("");
    try {
      const seeded = await seedDemoScenario(scenarioId);
      setDemoModalOpen(false);
      router.push(`/incidents/${encodeURIComponent(seeded.incident.id)}/analysis`);
    } catch (failure: unknown) {
      setSeedError(describeApiFailure(failure));
      setSeedingId(null);
    }
  }

  if (account.state === "loading") {
    return <p role="status" className="m1-hint">Loading operational telemetry…</p>;
  }

  if (account.state === "error") {
    return <p role="alert" className="m1-error">{account.message}</p>;
  }

  if (account.state === "signed-out") {
    const checkedAt = new Date(health.checkedAt).toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
    });
    return (
      <div className="signedout-simple">
        <section className="panel signedout-hero" aria-labelledby="workspace-access-heading">
          <div className="signedout-hero-copy">
            <h2 id="workspace-access-heading">Evidence-grounded incident response</h2>
            <p>
              Sign in to investigate live outages, inspect redacted log telemetry, or seed a realistic
              multi-service demo incident in one click.
            </p>
            <div className="m1-actions">
              <Link className="button button-primary" href="/login">Sign in</Link>
              <Link className="button button-outline" href="/register">Create account</Link>
            </div>
          </div>

          <ol className="signedout-steps" aria-label="Core workflow">
            {CAPABILITIES.map((cap) => (
              <li key={cap.step}>
                <span className="signedout-step-num">{cap.step}</span>
                <div>
                  <strong>{cap.title}</strong>
                  <p>{cap.desc}</p>
                </div>
              </li>
            ))}
          </ol>

          <p className="signedout-footnote">
            System check: {health.state === "operational" ? "API & dependencies ready" : "Degraded"} ·{" "}
            <time dateTime={health.checkedAt}>{checkedAt} UTC</time>
          </p>
        </section>
      </div>
    );
  }

  if (error) {
    return <p role="alert" className="m1-error">{error}</p>;
  }

  if (!summary) {
    return <p role="status" className="m1-hint">Loading dashboard summary…</p>;
  }

  const activeCount = summary.counts.open + summary.counts.investigating;
  const errorRate = formatErrorRate(
    summary.telemetry_totals.total_error_events,
    summary.telemetry_totals.total_events,
  );
  const maxServiceVolume = Math.max(
    1,
    ...summary.service_health.map((svc) => Math.max(svc.error_events, svc.event_count)),
  );
  const totalForSev = Math.max(
    1,
    summary.severity_breakdown.reduce((acc, row) => acc + row.count, 0),
  );

  return (
    <div className="dash-stack">
      <section className="panel dash-kpi-strip" aria-label="Operational summary">
        <div className="dash-kpi-cell">
          <span className="dash-kpi-label">Active incidents</span>
          <strong className={summary.counts.critical_open > 0 ? "dash-kpi-value is-alert" : "dash-kpi-value"}>
            {activeCount.toLocaleString()}
          </strong>
          <span className="dash-kpi-sub">
            {summary.counts.critical_open > 0
              ? `${summary.counts.critical_open} critical · ${summary.counts.investigating} investigating`
              : `${summary.counts.open} open · ${summary.counts.investigating} investigating`}
          </span>
        </div>

        <div className="dash-kpi-cell">
          <span className="dash-kpi-label">Ingested events</span>
          <strong className="dash-kpi-value">
            {summary.telemetry_totals.total_events.toLocaleString()}
          </strong>
          <span className="dash-kpi-sub">
            {errorRate} errors · {summary.telemetry_totals.total_sources.toLocaleString()} sources
          </span>
        </div>

        <div className="dash-kpi-cell">
          <span className="dash-kpi-label">Median MTTR</span>
          <strong className="dash-kpi-value">{formatDurationMinutes(summary.mttr_minutes)}</strong>
          <span className="dash-kpi-sub">
            {summary.counts.resolved} resolved of {summary.counts.total}
          </span>
        </div>

        <div className="dash-kpi-cell">
          <span className="dash-kpi-label">AI &amp; postmortems</span>
          <strong className="dash-kpi-value">
            {summary.telemetry_totals.total_investigations.toLocaleString()}
          </strong>
          <span className="dash-kpi-sub">
            {summary.telemetry_totals.total_snapshots} snapshots · {summary.telemetry_totals.total_postmortems} reports
          </span>
        </div>
      </section>

      <div className="dash-main-grid">
        <section className="panel" aria-labelledby="workspace-feed-heading">
          <div className="panel-header panel-header-with-actions dash-panel-bar">
            <div className="dash-panel-left">
              <h2 id="workspace-feed-heading" className="sr-only">Incidents and activity</h2>
              <div className="dash-underline-tabs" role="tablist" aria-label="Overview feed">
                <button
                  type="button"
                  role="tab"
                  aria-selected={feedTab === "incidents"}
                  className={feedTab === "incidents" ? "dash-underline-tab is-active" : "dash-underline-tab"}
                  onClick={() => setFeedTab("incidents")}
                >
                  Incidents
                  <span className="dash-tab-count">{summary.recent_incidents.length}</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={feedTab === "activity"}
                  className={feedTab === "activity" ? "dash-underline-tab is-active" : "dash-underline-tab"}
                  onClick={() => setFeedTab("activity")}
                >
                  Recent activity
                  {summary.recent_activity.length > 0 && (
                    <span className="dash-tab-count">{summary.recent_activity.length}</span>
                  )}
                </button>
              </div>
            </div>

            <div className="dash-panel-controls">
              {feedTab === "incidents" && (
                <div className="dash-filter-tabs" role="tablist" aria-label="Filter incidents by state">
                  {(
                    [
                      ["all", "All"],
                      ["active", "Active"],
                      ["resolved", "Resolved"],
                    ] as const
                  ).map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      role="tab"
                      aria-selected={statusFilter === key}
                      className={statusFilter === key ? "dash-filter-tab is-active" : "dash-filter-tab"}
                      onClick={() => setStatusFilter(key)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
              {scenarios.length > 0 && (
                <button
                  type="button"
                  className="quiet-btn"
                  onClick={() => {
                    setSeedError("");
                    setDemoModalOpen(true);
                  }}
                >
                  Try demo outage
                </button>
              )}
              <Link href="/incidents" className="quiet-link">
                All incidents →
              </Link>
            </div>
          </div>

          {feedTab === "incidents" ? (
            visibleIncidents.length === 0 ? (
              <div className="dash-empty-block">
                <p className="m1-hint" style={{ margin: 0 }}>
                  {summary.counts.total === 0
                    ? "No incidents yet. Create an incident or launch a realistic demo outage to explore."
                    : "No incidents match this filter."}
                </p>
                {summary.counts.total === 0 && scenarios.length > 0 && (
                  <div className="dash-onboarding-demos">
                    {scenarios.map((scenario) => (
                      <div className="demo-row" key={scenario.id}>
                        <div className="demo-row-main">
                          <div className="demo-row-head">
                            <strong>{scenario.title}</strong>
                            <span className={`if-badge if-badge-${scenario.severity}`}>{scenario.severity}</span>
                          </div>
                          <p className="demo-row-sub">{scenario.subtitle}</p>
                        </div>
                        <button
                          type="button"
                          className="quiet-btn"
                          disabled={seedingId !== null}
                          onClick={() => void launchDemo(scenario.id)}
                        >
                          {seedingId === scenario.id ? "Seeding…" : "Launch →"}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="table-scroll">
                <table className="incident-table m1-table dash-queue-table">
                  <thead>
                    <tr>
                      <th scope="col">Incident</th>
                      <th scope="col">Severity</th>
                      <th scope="col">Status</th>
                      <th scope="col">Events</th>
                      <th scope="col">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleIncidents.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <div className="dash-inc-title-cell">
                            <Link
                              className="m1-table-link"
                              href={`/incidents/${encodeURIComponent(item.id)}`}
                            >
                              {item.title}
                            </Link>
                            <span className="dash-inc-meta">
                              <span>INC-{item.id.slice(0, 6).toUpperCase()}</span>
                              <span>·</span>
                              <span>{item.service_name || "unassigned"}</span>
                              <span>·</span>
                              <span>{item.environment}</span>
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className={`if-badge if-badge-${item.severity}`}>{item.severity}</span>
                        </td>
                        <td>
                          <span className={`if-badge if-badge-${item.status}`}>{item.status}</span>
                        </td>
                        <td className="dash-telemetry-cell">
                          {item.event_count.toLocaleString()}
                          {item.error_count > 0 && (
                            <>
                              {" "}
                              <span className="dash-telemetry-err">
                                ({item.error_count.toLocaleString()} err)
                              </span>
                            </>
                          )}
                        </td>
                        <td className="m1-time" title={item.updated_at}>
                          {formatRelativeAge(item.updated_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          ) : summary.recent_activity.length === 0 ? (
            <div className="m1-empty">No workspace activity recorded yet.</div>
          ) : (
            <ol className="dash-activity-list">
              {summary.recent_activity.map((entry) => (
                <li className="dash-activity-item" key={entry.id}>
                  <span className={activityDotClass(entry.kind)} aria-hidden="true" />
                  <div className="dash-activity-body">
                    <span className="dash-activity-summary">{entry.summary}</span>
                    <Link
                      className="dash-activity-link"
                      href={`/incidents/${encodeURIComponent(entry.incident_id)}`}
                    >
                      {entry.incident_title}
                    </Link>
                  </div>
                  <time
                    className="dash-activity-time"
                    dateTime={entry.occurred_at}
                    title={entry.occurred_at}
                  >
                    {formatRelativeAge(entry.occurred_at)}
                  </time>
                </li>
              ))}
            </ol>
          )}
        </section>

        <aside className="panel dash-summary-rail" aria-label="Service health and severity">
          <div className="dash-rail-section">
            <h2 className="dash-rail-heading">Service impact</h2>
            {summary.service_health.length === 0 ? (
              <p className="m1-hint" style={{ margin: 0 }}>
                Ingest logs to view impacted services.
              </p>
            ) : (
              <div className="dash-svc-list">
                {summary.service_health.slice(0, 5).map((svc) => {
                  const pct = Math.max(
                    6,
                    Math.round(((svc.error_events || svc.event_count) / maxServiceVolume) * 100),
                  );
                  return (
                    <div className="dash-svc-row" key={svc.service}>
                      <div className="dash-svc-top">
                        <span className="dash-svc-name">{svc.service}</span>
                        <span className="dash-svc-stats">
                          {svc.error_events.toLocaleString()} err / {svc.event_count.toLocaleString()}
                        </span>
                      </div>
                      <div className="dash-bar-track" aria-hidden="true">
                        <span
                          className={svc.error_events > 0 ? "dash-bar-fill" : "dash-bar-fill is-ok"}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="dash-rail-section">
            <h2 className="dash-rail-heading">Severity mix</h2>
            <div className="dash-sev-bar" role="img" aria-label="Incident severity distribution">
              {summary.severity_breakdown.map((row) =>
                row.count > 0 ? (
                  <span
                    key={row.severity}
                    className={`dash-sev-seg-${row.severity}`}
                    style={{ width: `${(row.count / totalForSev) * 100}%` }}
                    title={`${row.severity}: ${row.count}`}
                  />
                ) : null,
              )}
            </div>
            <div className="dash-sev-legend">
              {summary.severity_breakdown.map((row) => (
                <div className="dash-sev-item" key={row.severity}>
                  <span className="dash-sev-dot-wrap">
                    <span className={`dash-sev-dot dash-sev-seg-${row.severity}`} aria-hidden="true" />
                    {row.severity}
                  </span>
                  <span className="dash-sev-count">
                    {row.count}
                    {row.open_count > 0 ? ` (${row.open_count})` : ""}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>

      {demoModalOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) setDemoModalOpen(false);
          }}
        >
          <div
            className="modal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="demo-modal-title"
          >
            <div className="modal-header">
              <div>
                <h2 id="demo-modal-title">Launch a demo outage</h2>
                <p>Seeds realistic multi-service logs, burst anomalies, trace links, and a redacted snapshot.</p>
              </div>
              <button
                type="button"
                className="drawer-close-btn"
                aria-label="Close demo outage dialog"
                onClick={() => setDemoModalOpen(false)}
              >
                ✕
              </button>
            </div>

            {seedError && (
              <div style={{ padding: "12px 20px 0" }}>
                <p role="alert" className="m1-error" style={{ margin: 0 }}>{seedError}</p>
              </div>
            )}

            <div className="modal-list">
              {scenarios.map((scenario) => {
                const isSeeding = seedingId === scenario.id;
                return (
                  <div className="demo-row" key={scenario.id}>
                    <div className="demo-row-main">
                      <div className="demo-row-head">
                        <strong>{scenario.title}</strong>
                        <span className={`if-badge if-badge-${scenario.severity}`}>
                          {scenario.severity}
                        </span>
                      </div>
                      <p className="demo-row-sub">{scenario.subtitle}</p>
                      <span className="dash-inc-meta">
                        <span>{scenario.services.join(" · ")}</span>
                      </span>
                    </div>
                    <button
                      type="button"
                      className="demo-launch-btn"
                      disabled={seedingId !== null}
                      onClick={() => void launchDemo(scenario.id)}
                    >
                      {isSeeding ? "Seeding…" : "Launch →"}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
