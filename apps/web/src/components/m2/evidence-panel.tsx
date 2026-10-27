"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, describeApiFailure } from "@/lib/api-client";

type Source = { id: string; filename: string; sha256: string; byte_size: number; state: string; accepted: number; rejected: number; warnings: {code: string; count: number}[] };
type Job = { id: string; state: string; accepted: number; rejected: number; error_code: string };
type Event = { id: string; source_id: string; line_start: number; occurred_at: string | null; timestamp_quality: string; severity: string; message: string };

export function EvidencePanel({ incidentId }: { incidentId: string }) {
  const [files, setFiles] = useState<File[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    const [nextSources, nextEvents] = await Promise.all([
      apiGet<Source[]>(`incidents/${incidentId}/sources`),
      apiGet<{ results: Event[] }>(`incidents/${incidentId}/events`),
    ]);
    setSources(nextSources);
    setEvents(nextEvents.results);
  }, [incidentId]);

  useEffect(() => {
    let cancelled = false;
    const update = async () => {
      try {
        const [nextSources, nextEvents] = await Promise.all([
          apiGet<Source[]>(`incidents/${incidentId}/sources`),
          apiGet<{ results: Event[] }>(`incidents/${incidentId}/events`),
        ]);
        if (!cancelled) { setSources(nextSources); setEvents(nextEvents.results); }
      } catch { if (!cancelled) setMessage("Evidence could not be loaded."); }
    };
    void update();
    return () => { cancelled = true; };
  }, [incidentId]);

  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!files.length) return;
    setBusy(true); setMessage("");
    try {
      const csrfResponse = await apiGet<{ csrf_token: string }>("auth/csrf");
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      const response = await fetch(`/api/v1/incidents/${incidentId}/uploads`, {
        method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrfResponse.csrf_token }, body: form,
      });
      const contentType = response.headers.get("content-type") ?? "";
      if (!contentType.includes("json")) {
        throw new Error(
          `Upload failed (HTTP ${response.status}). ` +
          "The server returned an unexpected response. Check the API logs."
        );
      }

      const payload = await response.json();

      if (!response.ok) {
        throw new Error(
          payload.detail || `Upload rejected (HTTP ${response.status}).`
        );
      }
      setJob({ id: payload.job_id, state: payload.state, accepted: 0, rejected: 0, error_code: "" });
      setFiles([]); setMessage("Upload accepted. Processing will continue in the worker.");
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : describeApiFailure(error)); }
    finally { setBusy(false); }
  }

  async function checkJob() {
    if (!job) return;
    try { setJob(await apiGet<Job>(`incidents/${incidentId}/jobs/${job.id}`)); await refresh(); }
    catch (error) { setMessage(describeApiFailure(error)); }
  }

  return (
    <section className="m2-panel" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading">Log evidence</h2>
      <p>Upload UTF-8 .log, .txt, .jsonl or .json files. Up to five files, 25 MiB each. Personal data and secrets may occur in logs; use sanitized test data.</p>
      <form onSubmit={upload}>
        <label htmlFor="log-files">Log files</label>
        <input id="log-files" type="file" multiple accept=".log,.txt,.jsonl,.json" onChange={event => setFiles(Array.from(event.currentTarget.files || []))} />
        <button type="submit" disabled={busy || files.length === 0 || files.length > 5}>{busy ? "Uploading…" : "Upload evidence"}</button>
      </form>
      <p role="status" aria-live="polite">{message}</p>
      {job && <p>Job: {job.state} — {job.accepted} accepted, {job.rejected} rejected <button type="button" onClick={() => void checkJob()}>Refresh job</button></p>}
      <h3>Sources</h3>
      {sources.length === 0 ? <p>No sources uploaded.</p> : <ul>{sources.map(source => <li key={source.id}>{source.filename} — {source.state} — {source.accepted} accepted, {source.rejected} rejected — SHA-256: <code>{source.sha256.slice(0, 16)}…</code>{source.warnings.length > 0 && <span> — {source.warnings.map(w => `${w.code} (${w.count})`).join(", ")}</span>}</li>)}</ul>}
      <h3>Normalized events</h3>
      {events.length === 0 ? <p>No parsed events.</p> : <table><caption>Most recently observed log records</caption><thead><tr><th scope="col">Timestamp</th><th scope="col">Severity</th><th scope="col">Redacted message</th><th scope="col">Source line</th></tr></thead><tbody>{events.map(record => <tr key={record.id}><td>{record.occurred_at || `Unknown (${record.timestamp_quality})`}</td><td>{record.severity || "—"}</td><td>{record.message}</td><td>{record.line_start}</td></tr>)}</tbody></table>}
    </section>
  );
}
