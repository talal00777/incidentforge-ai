"use client";

import { useEffect, useState } from "react";
import { apiGet, describeApiFailure } from "@/lib/api-client";

type Bucket = { start: string; total: number; errors: number };
type Breakdown = { severity: string; count: number };
type Service = { service: string; count: number };
type Group = { fingerprint: string; count: number; event_ids: string[] };
type Analysis = {
  algorithm_version: string;
  input_sha256: string;
  total_events: number;
  error_events: number;
  missing_event_time: number;
  severity_counts: Breakdown[];
  service_counts: Service[];
  fingerprint_groups: Group[];
  timeline: Bucket[];
  anomaly: { status: string; reason?: string; buckets: string[] };
  limitations: string[];
};

export function AnalysisPanel({ incidentId }: { incidentId: string }) {
  const [data, setData] = useState<Analysis | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [bucket, setBucket] = useState("5");

  useEffect(() => {
    let active = true;
    apiGet<Analysis>(`incidents/${encodeURIComponent(incidentId)}/analysis?bucket_minutes=${bucket}`)
      .then(result => { if (active) { setData(result); setError(""); } })
      .catch(failure => { if (active) { setData(null); setError(describeApiFailure(failure)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [incidentId, bucket]);

  return (
    <section className="panel" aria-labelledby="analysis-heading">
      <h2 id="analysis-heading">Incident analysis</h2>
      <p>Deterministic aggregates from normalized evidence. Counts are log event counts, not request failure rates.</p>
      <label htmlFor="analysis-bucket">Timeline bucket</label>{" "}
      <select id="analysis-bucket" value={bucket} onChange={event => { setLoading(true); setBucket(event.target.value); }}>
        <option value="1">1 minute</option><option value="5">5 minutes</option>
        <option value="15">15 minutes</option><option value="60">60 minutes</option>
      </select>
      {loading && <p role="status">Loading analysis…</p>}
      {error && <p role="alert">{error}</p>}
      {data && !loading && <>
        <p><strong>{data.total_events}</strong> events · <strong>{data.error_events}</strong> error-level events · {data.missing_event_time} without occurrence timestamps</p>
        <h3>Timeline</h3>
        {data.timeline.length === 0 ? <p>No events have explicit occurrence timestamps.</p> :
          <table><caption>Event counts per {bucket}-minute time bucket (UTC)</caption><thead><tr><th scope="col">Window start (UTC)</th><th scope="col">Events</th><th scope="col">Errors</th></tr></thead><tbody>
            {data.timeline.map(item => <tr key={item.start}><td><time dateTime={item.start}>{item.start}</time></td><td>{item.total}</td><td>{item.errors}</td></tr>)}
          </tbody></table>}
        <h3>Severity breakdown</h3>
        <table><caption>Event counts by severity</caption><thead><tr><th scope="col">Severity</th><th scope="col">Events</th></tr></thead><tbody>{data.severity_counts.map(item => <tr key={item.severity}><td>{item.severity}</td><td>{item.count}</td></tr>)}</tbody></table>
        <h3>Services</h3>
        <ul>{data.service_counts.map(item => <li key={item.service}>{item.service}: {item.count}</li>)}</ul>
        <h3>Top normalized fingerprints</h3>
        <ul>{data.fingerprint_groups.map(item => <li key={item.fingerprint}><code>{item.fingerprint.slice(0, 16)}</code> · {item.count} events · {item.event_ids.length} sample event IDs</li>)}</ul>
        <h3>Burst detection</h3>
        <p>{data.anomaly.status === "insufficient_data" ? `Insufficient data: ${data.anomaly.reason}` : `${data.anomaly.buckets.length} unusually busy time buckets flagged by heuristic analysis.`}</p>
        {data.limitations.map(item => <p key={item}>{item}</p>)}
        <p><small>Algorithm {data.algorithm_version} · Input SHA-256 <code>{data.input_sha256.slice(0, 16)}…</code></small></p>
      </>}
    </section>
  );
}
