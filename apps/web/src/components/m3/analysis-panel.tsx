"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AnalysisCharts } from "@/components/m3/analysis-charts";
import { apiGet, describeApiFailure } from "@/lib/api-client";
import { eventTimeLabel, type IncidentAnalysis } from "@/lib/analysis-display";

import styles from "./incident-analysis.module.css";

type Timezone = "utc" | "local";

export function AnalysisPanel({ incidentId }: { incidentId: string }) {
  const [data, setData] = useState<IncidentAnalysis | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [bucket, setBucket] = useState("5");
  const [zone, setZone] = useState<Timezone>("utc");

  useEffect(() => {
    let active = true;
    apiGet<IncidentAnalysis>(`incidents/${encodeURIComponent(incidentId)}/analysis?bucket_minutes=${bucket}`)
      .then((result) => {
        if (active) {
          setData(result);
          setError("");
        }
      })
      .catch((failure) => {
        if (active) {
          setData(null);
          setError(describeApiFailure(failure));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [incidentId, bucket]);

  const recurring = data?.fingerprint_groups.filter((group) => group.count > 1).length ?? 0;
  const metrics = data ? [
    { name: "Total events", value: data.total_events, tone: "" },
    { name: "Error-level", value: data.error_events, tone: styles.errorTone },
    { name: "Recurring patterns", value: recurring, tone: styles.patternTone },
    { name: "Unknown time", value: data.missing_event_time, tone: styles.unknownTone },
  ] : [];

  return (
    <div className={styles.root} aria-busy={loading}>
      <header className={styles.pageHeader}>
        <div className={styles.headingBlock}>
          <h1 className={styles.pageTitle}>Incident analysis</h1>
        </div>
        <div className={styles.headerActions}>
          <div className={styles.controlSet}>
            <label className={styles.intervalLabel} htmlFor="analysis-bucket">
              <span>Interval</span>
              <select
                id="analysis-bucket"
                className={styles.intervalSelect}
                value={bucket}
                onChange={(event) => { setLoading(true); setBucket(event.target.value); }}
              >
                <option value="1">1 minute</option>
                <option value="5">5 minutes</option>
                <option value="15">15 minutes</option>
                <option value="60">1 hour</option>
              </select>
            </label>
            <div className={styles.zoneToggle} role="group" aria-label="Chart timezone">
              <button type="button" aria-pressed={zone === "utc"} className={zone === "utc" ? styles.zoneSelected : ""} onClick={() => setZone("utc")}>UTC</button>
              <button type="button" aria-pressed={zone === "local"} className={zone === "local" ? styles.zoneSelected : ""} onClick={() => setZone("local")}>Local</button>
            </div>
          </div>
          <Link className={styles.backLink} href={`/incidents/${encodeURIComponent(incidentId)}/sources`}>
            <span aria-hidden="true">←</span><span>Evidence &amp; sources</span>
          </Link>
        </div>
      </header>

      {loading && <div className={styles.loading} role="status">Loading analysis…</div>}
      {error && <div className={styles.alert} role="alert">{error}</div>}

      {data && !loading && (
        <>
          <section className={styles.metrics} aria-label="Incident totals">
            {metrics.map((metric) => (
              <div className={`${styles.metric} ${metric.tone}`} key={metric.name}>
                <span className={styles.metricLabel}>{metric.name}</span>
                <strong className={styles.metricValue}>{metric.value.toLocaleString()}</strong>
              </div>
            ))}
          </section>

          <AnalysisCharts data={data} bucket={bucket} zone={zone} />

          <section className={styles.detailsCard} aria-labelledby="analysis-data-heading">
            <div className={styles.detailsHeading}>
              <h2 id="analysis-data-heading">Data tables</h2>
            </div>
            <div className={styles.detailsList}>
              <details className={styles.detail}>
                <summary>Timeline <span>{data.timeline.length.toLocaleString()} windows</span></summary>
                <div className={styles.tableWrap}><table className={styles.table}><caption>Events per UTC interval</caption><thead><tr><th scope="col">UTC window</th><th scope="col">Events</th><th scope="col">Errors</th></tr></thead><tbody>
                  {data.timeline.map((item) => <tr key={item.start}><td><time dateTime={item.start}>{eventTimeLabel(item.start, "utc")}</time></td><td>{item.total}</td><td>{item.errors}</td></tr>)}
                </tbody></table></div>
              </details>
              <details className={styles.detail}>
                <summary>Severity <span>{data.severity_counts.length} levels</span></summary>
                <div className={styles.tableWrap}><table className={styles.table}><caption>Events by severity</caption><thead><tr><th scope="col">Severity</th><th scope="col">Events</th></tr></thead><tbody>
                  {data.severity_counts.map((item) => <tr key={item.severity}><td>{item.severity || "UNKNOWN"}</td><td>{item.count}</td></tr>)}
                </tbody></table></div>
              </details>
              <details className={styles.detail}>
                <summary>Services <span>{data.service_counts.length} shown</span></summary>
                <div className={styles.tableWrap}><table className={styles.table}><caption>Service event counts</caption><thead><tr><th scope="col">Service</th><th scope="col">Events</th><th scope="col">Error-level</th></tr></thead><tbody>
                  {data.service_counts.map((item) => <tr key={item.service}><td>{item.service || "Unknown service"}</td><td>{item.count}</td><td>{item.error_events}</td></tr>)}
                </tbody></table></div>
              </details>
              <details className={styles.detail}>
                <summary>Fingerprints <span>{data.fingerprint_groups.length} groups</span></summary>
                <div className={styles.tableWrap}><table className={styles.table}><caption>Normalized fingerprint counts</caption><thead><tr><th scope="col">Fingerprint</th><th scope="col">Events</th><th scope="col">Examples</th></tr></thead><tbody>
                  {data.fingerprint_groups.map((item) => <tr key={item.fingerprint}><td><code title={item.fingerprint}>{item.fingerprint.slice(0, 12)}…</code></td><td>{item.count}</td><td>{item.event_ids.length}</td></tr>)}
                </tbody></table></div>
              </details>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
