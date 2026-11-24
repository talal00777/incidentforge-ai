"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { StatusPanel } from "@/components/status-panel";
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

const PIPELINE_SPECS = [
  {
    code: "STAGE 01 · INGESTION",
    title: "Bounded parsing & PII redaction",
    desc: "Line-provenance JSON/syslog/traceback ingestion with deterministic secret scrubbing and SHA-256 source digests.",
  },
  {
    code: "STAGE 02 · TELEMETRY",
    title: "LOO-MAD bursts & trace correlation",
    desc: "Time-bucketed error spikes, template fingerprinting, and cross-service transition graphs over shared trace IDs.",
  },
  {
    code: "STAGE 03 · GROUNDED AI",
    title: "Consented snapshots & citation checks",
    desc: "Frozen redacted evidence packages paired with provider-agnostic 3-stage AI synthesis and strict event citations.",
  },
  {
    code: "STAGE 04 · GOVERNANCE",
    title: "Human adjudication & immutable exports",
    desc: "Explicit hypothesis sign-off separated from AI output, producing checksummed versioned PDF and JSON postmortems.",
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
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
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
      router.push(`/incidents/${encodeURIComponent(seeded.incident.id)}/analysis`);
    } catch (failure: unknown) {
      setSeedError(describeApiFailure(failure));
      setSeedingId(null);
    }
  }

  if (account.state === "loading") {
    return (
      <div className="dash-stack">
        <p role="status" className="m1-hint">Loading operational telemetry…</p>
        <StatusPanel health={health} />
      </div>
    );
  }

  if (account.state === "error") {
    return (
      <div className="dash-stack">
        <p role="alert" className="m1-error">{account.message}</p>
        <StatusPanel health={health} />
      </div>
    );
  }

  if (account.state === "signed-out") {
    return (
      <div className="signedout-grid">
        <div className="dash-stack">
          <section className="panel m1-prompt" aria-labelledby="workspace-access-heading">
            <h2 id="workspace-access-heading">Operations workspace</h2>
            <p>
              Sign in to inspect live incident telemetry, launch realistic multi-service demo outages,
              and run evidence-grounded AI investigations.
            </p>
            <div className="m1-actions">
              <Link className="button button-primary" href="/login">Sign in</Link>
              <Link className="button button-outline" href="/register">Create account</Link>
            </div>
          </section>

          <section className="panel" aria-labelledby="architecture-heading">
            <div className="panel-header">
              <div>
                <h2 id="architecture-heading">Investigation pipeline</h2>
                <p>Deterministic log analytics through audited postmortem generation.</p>
              </div>
            </div>
            <div className="spec-grid">
              {PIPELINE_SPECS.map((spec) => (
                <article className="spec-item" key={spec.code}>
                  <span className="spec-code">{spec.code}</span>
                  <strong>{spec.title}</strong>
                  <p>{spec.desc}</p>
                </article>
              ))}
            </div>
          </section>
        </div>

        <div className="dash-rail">
          <StatusPanel health={health} />
          <section className="panel" aria-labelledby="sandbox-preview-heading">
            <div className="panel-header">
              <div>
                <h2 id="sandbox-preview-heading">Realistic outage sandbox</h2>
                <p>Available immediately after sign-in.</p>
              </div>
            </div>
            <div className="dash-card-body">
              <p className="m1-hint" style={{ margin: 0 }}>
                Seed multi-service production failure telemetry (Checkout DB pool exhaustion, Auth JWKS
                rotation drift, or Redis cache stampede) with one click through the real parsing and
                redaction pipeline.
              </p>
            </div>
          </section>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dash-stack">
        <p role="alert" className="m1-error">{error}</p>
        <StatusPanel health={health} />
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="dash-stack">
        <p role="status" className="m1-hint">Loading dashboard summary…</p>
        <StatusPanel health={health} />
      </div>
    );
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
      <section className="dash-kpi-grid" aria-label="Operational telemetry summary">
        <article className={summary.counts.critical_open > 0 ? "dash-kpi-card is-critical" : "dash-kpi-card"}>
          <div className="dash-kpi-head">
            <h2 className="dash-kpi-label">Active incidents</h2>
            {summary.counts.critical_open > 0 && (
              <span className="if-badge if-badge-critical">{summary.counts.critical_open} critical</span>
            )}
          </div>
          <p className="dash-kpi-value">{activeCount.toLocaleString()}</p>
          <p className="dash-kpi-sub">
            {summary.counts.open} open · {summary.counts.investigating} investigating
          </p>
        </article>

        <article className="dash-kpi-card is-telemetry">
          <div className="dash-kpi-head">
            <h2 className="dash-kpi-label">Ingested events</h2>
            <span className="m2-count-pill">{errorRate} err</span>
          </div>
          <p className="dash-kpi-value">{summary.telemetry_totals.total_events.toLocaleString()}</p>
          <p className="dash-kpi-sub">
            {summary.telemetry_totals.total_sources.toLocaleString()} log sources ·{" "}
            {summary.telemetry_totals.total_error_events.toLocaleString()} errors
          </p>
        </article>

        <article className="dash-kpi-card is-mttr">
          <div className="dash-kpi-head">
            <h2 className="dash-kpi-label">Median MTTR</h2>
          </div>
          <p className="dash-kpi-value">{formatDurationMinutes(summary.mttr_minutes)}</p>
          <p className="dash-kpi-sub">
            {summary.counts.resolved} resolved · {summary.counts.total} total tracked
          </p>
        </article>

        <article className="dash-kpi-card is-ai">
          <div className="dash-kpi-head">
            <h2 className="dash-kpi-label">AI &amp; postmortems</h2>
          </div>
          <p className="dash-kpi-value">
            {summary.telemetry_totals.total_investigations.toLocaleString()}
          </p>
          <p className="dash-kpi-sub">
            {summary.telemetry_totals.total_snapshots} snapshots ·{" "}
            {summary.telemetry_totals.total_postmortems} postmortems
          </p>
        </article>
      </section>

      <div className="dash-main-grid">
        <section className="panel" aria-labelledby="recent-incidents-heading">
          <div className="panel-header panel-header-with-actions">
            <div>
              <h2 id="recent-incidents-heading">Incident queue</h2>
              <p>Live records with ingested telemetry.</p>
            </div>
            <div className="m1-actions">
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
              <Link href="/incidents" className="button button-outline" style={{ minHeight: "36px", padding: "0 12px", fontSize: "12.5px" }}>
                Browse all
              </Link>
            </div>
          </div>

          {visibleIncidents.length === 0 ? (
            <div className="m1-empty">
              {summary.counts.total === 0
                ? "No incidents tracked yet. Create one or launch a realistic demo outage below."
                : "No incidents match the selected status filter."}
            </div>
          ) : (
            <div className="table-scroll">
              <table className="incident-table m1-table dash-queue-table">
                <thead>
                  <tr>
                    <th scope="col">Incident</th>
                    <th scope="col">Severity</th>
                    <th scope="col">Status</th>
                    <th scope="col">Telemetry</th>
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
                            <Link
                              className="dash-row-action"
                              href={
                                item.event_count > 0
                                  ? `/incidents/${encodeURIComponent(item.id)}/analysis`
                                  : `/incidents/${encodeURIComponent(item.id)}/sources`
                              }
                            >
                              {item.event_count > 0 ? "Analysis →" : "Logs →"}
                            </Link>
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
                        {item.event_count.toLocaleString()} ev
                        {item.error_count > 0 && (
                          <>
                            {" · "}
                            <span className="dash-telemetry-err">
                              {item.error_count.toLocaleString()} err
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
          )}
        </section>

        <div className="dash-rail">
          <section className="panel" aria-labelledby="service-impact-heading">
            <div className="panel-header">
              <div>
                <h2 id="service-impact-heading">Service error impact</h2>
                <p>Top services ranked by error volume.</p>
              </div>
            </div>
            <div className="dash-card-body">
              {summary.service_health.length === 0 ? (
                <p className="m1-hint" style={{ margin: 0 }}>
                  Ingest logs or launch a demo outage to populate service error telemetry.
                </p>
              ) : (
                summary.service_health.map((svc) => {
                  const pct = Math.max(
                    6,
                    Math.round(((svc.error_events || svc.event_count) / maxServiceVolume) * 100),
                  );
                  return (
                    <div className="dash-svc-row" key={svc.service}>
                      <div className="dash-svc-top">
                        <span className="dash-svc-name">{svc.service}</span>
                        <span className="dash-svc-stats">
                          {svc.error_events.toLocaleString()} err / {svc.event_count.toLocaleString()} ev
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
                })
              )}
            </div>
          </section>

          <section className="panel" aria-labelledby="severity-breakdown-heading">
            <div className="panel-header">
              <div>
                <h2 id="severity-breakdown-heading">Severity breakdown</h2>
                <p>Total vs. active incidents by severity tier.</p>
              </div>
            </div>
            <div className="dash-card-body">
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
                      {row.open_count > 0 ? ` (${row.open_count} open)` : ""}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <StatusPanel health={health} />
        </div>
      </div>

      <div className="dash-lower-grid">
        <section className="panel" aria-labelledby="activity-stream-heading">
          <div className="panel-header">
            <div>
              <h2 id="activity-stream-heading">Recent activity</h2>
              <p>Chronological audit, ingestion, AI, and postmortem events.</p>
            </div>
          </div>
          {summary.recent_activity.length === 0 ? (
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

        <section className="panel" aria-labelledby="demo-scenarios-heading">
          <div className="panel-header">
            <div>
              <h2 id="demo-scenarios-heading">Realistic demo outages</h2>
              <p>
                Seed multi-service production logs, burst anomalies, trace chains, and a frozen
                redacted snapshot in one click.
              </p>
            </div>
          </div>

          {seedError && (
            <div style={{ padding: "12px 18px 0" }}>
              <p role="alert" className="m1-error" style={{ margin: 0 }}>{seedError}</p>
            </div>
          )}

          <div className="demo-grid">
            {scenarios.length === 0 ? (
              <p className="m1-hint" style={{ margin: 0 }}>
                Demo outage presets are currently unavailable.
              </p>
            ) : (
              scenarios.map((scenario) => {
                const isSeeding = seedingId === scenario.id;
                return (
                  <article className="demo-card" key={scenario.id}>
                    <div className="demo-card-top">
                      <div>
                        <h3 className="demo-card-title">{scenario.title}</h3>
                        <p className="demo-card-sub">{scenario.subtitle}</p>
                      </div>
                      <span className={`if-badge if-badge-${scenario.severity}`}>
                        {scenario.severity}
                      </span>
                    </div>

                    <div className="demo-chip-row" aria-label="Involved services">
                      {scenario.services.map((svc) => (
                        <span className="demo-svc-chip" key={svc}>{svc}</span>
                      ))}
                      {scenario.expected_signals.slice(0, 2).map((signal) => (
                        <span className="demo-signal-chip" key={signal}>{signal}</span>
                      ))}
                    </div>

                    <div className="demo-card-footer">
                      <span className="dash-inc-meta">
                        <span>{scenario.environment}</span>
                        <span>·</span>
                        <span>3 log sources + snapshot</span>
                      </span>
                      <button
                        type="button"
                        className="demo-launch-btn"
                        disabled={seedingId !== null}
                        onClick={() => void launchDemo(scenario.id)}
                      >
                        {isSeeding ? "Seeding telemetry…" : "Launch scenario →"}
                      </button>
                    </div>
                  </article>
                );
              })
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
