"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAccount } from "@/components/m1/use-account";
import { apiGet, describeApiFailure } from "@/lib/api-client";
import {
  describeTime,
  formatLineRange,
  selectVisibleEvents,
  type DisplayTimezone,
  type EventSort,
  type EvidenceEvent,
} from "@/lib/evidence-display";

type Source = {
  id: string;
  filename: string;
  sha256: string;
  byte_size: number;
  state: string;
  accepted: number;
  rejected: number;
  warnings: { code: string; count: number }[];
};
type Job = { id: string; state: string; accepted: number; rejected: number; error_code: string };
type EventPage = { count: number; next: string | null; previous: string | null; results: EvidenceEvent[] };

const ACTIVE_JOB_STATES = new Set(["queued", "running"]);
const SEVERITIES = ["", "DEBUG", "INFO", "NOTICE", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"];

function severityTone(severity: string): string {
  const normalized = severity.toUpperCase();
  if (normalized === "ERROR" || normalized === "FATAL" || normalized === "CRITICAL") return "m2-sev m2-sev-error";
  if (normalized === "WARN" || normalized === "WARNING") return "m2-sev m2-sev-warn";
  if (normalized === "INFO" || normalized === "NOTICE") return "m2-sev m2-sev-info";
  return "m2-sev m2-sev-debug";
}

function sourceStateTone(state: string): string {
  const normalized = state.toLowerCase();
  if (normalized === "completed" || normalized === "parsed") return "if-badge if-badge-resolved";
  if (normalized === "failed" || normalized === "rejected") return "if-badge if-badge-critical";
  if (normalized === "running" || normalized === "queued" || normalized === "processing") {
    return "if-badge if-badge-investigating";
  }
  return "if-badge if-badge-neutral";
}

export function EvidencePanel({ incidentId }: { incidentId: string }) {
  const account = useAccount();
  const encodedIncident = encodeURIComponent(incidentId);
  const [files, setFiles] = useState<File[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [events, setEvents] = useState<EvidenceEvent[]>([]);
  const [totalEvents, setTotalEvents] = useState(0);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrevious, setHasPrevious] = useState(false);
  const [severityFilter, setSeverityFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOrder, setSortOrder] = useState<EventSort>("latest");
  const [zone, setZone] = useState<DisplayTimezone>("utc");
  const [job, setJob] = useState<Job | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const fetchEvidence = useCallback(async () => {
    const params = new URLSearchParams({ page: String(page), page_size: "50" });
    if (severityFilter) params.set("severity", severityFilter);
    if (sourceFilter) params.set("source_id", sourceFilter);
    if (searchQuery) params.set("search", searchQuery);
    params.set(
      "sort",
      sortOrder === "source" ? "source" : sortOrder === "earliest" ? "occurred_asc" : "occurred_desc",
    );
    const [nextSources, nextEvents] = await Promise.all([
      apiGet<Source[]>(`incidents/${encodedIncident}/sources`),
      apiGet<EventPage>(`incidents/${encodedIncident}/events?${params}`),
    ]);
    return { nextSources, nextEvents };
  }, [encodedIncident, page, searchQuery, severityFilter, sortOrder, sourceFilter]);

  const loadEvidence = useCallback(async () => {
    const { nextSources, nextEvents } = await fetchEvidence();
    setSources(nextSources);
    setEvents(nextEvents.results);
    setTotalEvents(nextEvents.count);
    setHasNext(nextEvents.next !== null);
    setHasPrevious(nextEvents.previous !== null);
  }, [fetchEvidence]);

  useEffect(() => {
    if (account.state !== "signed-in") return;
    let cancelled = false;
    fetchEvidence()
      .then(({ nextSources, nextEvents }) => {
        if (cancelled) return;
        setSources(nextSources);
        setEvents(nextEvents.results);
        setTotalEvents(nextEvents.count);
        setHasNext(nextEvents.next !== null);
        setHasPrevious(nextEvents.previous !== null);
      })
      .catch((failure: unknown) => {
        if (!cancelled) setMessage(describeApiFailure(failure));
      });
    return () => {
      cancelled = true;
    };
  }, [account.state, fetchEvidence]);

  const jobId = job?.id;
  const jobState = job?.state;
  useEffect(() => {
    if (account.state !== "signed-in" || !jobId || !jobState || !ACTIVE_JOB_STATES.has(jobState)) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await apiGet<Job>(`incidents/${encodedIncident}/jobs/${encodeURIComponent(jobId)}`);
        if (cancelled) return;
        setJob(next);
        if (!ACTIVE_JOB_STATES.has(next.state)) {
          await loadEvidence();
        }
      } catch (error) {
        if (!cancelled) setMessage(describeApiFailure(error));
      }
    };
    const timer = window.setInterval(() => void poll(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [account.state, encodedIncident, jobId, jobState, loadEvidence]);

  const visibleEvents = useMemo(
    () =>
      selectVisibleEvents(events, {
        query: searchQuery,
        severity: severityFilter,
        sourceId: sourceFilter,
        sort: sortOrder,
      }),
    [events, searchQuery, severityFilter, sourceFilter, sortOrder],
  );

  if (account.state === "loading") return <p role="status" className="m1-empty">Checking your session…</p>;
  if (account.state === "error") return <p role="alert" className="m1-error">{account.message}</p>;
  if (account.state === "signed-out") {
    return (
      <section className="panel m1-prompt" aria-labelledby="evidence-signin-heading">
        <h2 id="evidence-signin-heading">Sign in required</h2>
        <p>Please <Link href="/login">sign in</Link> to upload and inspect incident evidence.</p>
      </section>
    );
  }

  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!files.length) return;
    setBusy(true);
    setMessage("");
    try {
      const csrfResponse = await apiGet<{ csrf_token: string }>("auth/csrf");
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      const response = await fetch(`/api/v1/incidents/${encodedIncident}/uploads`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfResponse.csrf_token },
        body: form,
      });
      const contentType = response.headers.get("content-type") ?? "";
      if (!contentType.includes("json")) {
        throw new Error(
          `Upload failed (HTTP ${response.status}). The server returned an unexpected response. Check the API logs.`,
        );
      }

      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.detail || `Upload rejected (HTTP ${response.status}).`);
      }
      setJob({ id: payload.job_id, state: payload.state, accepted: 0, rejected: 0, error_code: "" });
      setFiles([]);
      setMessage("Upload accepted. Processing will continue in the worker.");
      await loadEvidence();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : describeApiFailure(error));
    } finally {
      setBusy(false);
    }
  }

  async function checkJob() {
    if (!job) return;
    try {
      setJob(await apiGet<Job>(`incidents/${encodedIncident}/jobs/${encodeURIComponent(job.id)}`));
      await loadEvidence();
    } catch (error) {
      setMessage(describeApiFailure(error));
    }
  }

  return (
    <div className="m2-panel">
      <section className="m2-card" aria-labelledby="evidence-heading">
        <div className="m2-card-header">
          <div>
            <h2 id="evidence-heading">Log evidence</h2>
            <p>Upload UTF-8 .log, .txt, .jsonl or .json files (up to 5 files, 25 MiB each). Use sanitized data; secrets are redacted during ingestion.</p>
          </div>
        </div>
        <div className="m2-card-body">
          <form className="m2-upload-form" onSubmit={upload}>
            <div className="m2-file-field">
              <label htmlFor="log-files">Log files</label>
              <input
                id="log-files"
                type="file"
                multiple
                accept=".log,.txt,.jsonl,.json"
                onChange={(event) => setFiles(Array.from(event.currentTarget.files || []))}
              />
            </div>
            <button
              className="button button-primary"
              type="submit"
              disabled={busy || files.length === 0 || files.length > 5}
            >
              {busy ? "Uploading…" : "Upload evidence"}
            </button>
          </form>

          <p className="m2-status-message" role="status" aria-live="polite">{message}</p>

          {job && (
            <div className="m2-status-banner" role="status">
              <span>
                <strong>Ingestion job:</strong> {job.state} · {job.accepted} accepted, {job.rejected} rejected
                {job.error_code ? ` (${job.error_code})` : ""}
              </span>
              <button className="button button-outline" type="button" onClick={() => void checkJob()}>
                Refresh job
              </button>
            </div>
          )}
        </div>
      </section>

      <section className="m2-card" aria-labelledby="sources-heading">
        <div className="m2-card-header">
          <div>
            <h3 id="sources-heading">Uploaded sources</h3>
            <p>Ingested files with SHA-256 provenance and line parsing counts.</p>
          </div>
          <span className="m2-count-pill">{sources.length} {sources.length === 1 ? "file" : "files"}</span>
        </div>
        {sources.length === 0 ? (
          <p className="m2-empty">No sources uploaded yet.</p>
        ) : (
          <ul className="m2-source-list">
            {sources.map((source) => (
              <li className="m2-source-item" key={source.id}>
                <div className="m2-source-primary">
                  <span className="m2-source-name">{source.filename}</span>
                  <div className="m2-source-meta">
                    <span>{source.accepted.toLocaleString()} accepted</span>
                    <span>{source.rejected.toLocaleString()} rejected</span>
                    <code className="m2-hash-chip" title={source.sha256}>SHA-256 {source.sha256.slice(0, 12)}…</code>
                    {source.warnings.map((w) => (
                      <span className="m2-warning-chip" key={w.code}>{w.code} ({w.count})</span>
                    ))}
                  </div>
                </div>
                <span className={sourceStateTone(source.state)}>{source.state}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="m2-card" aria-labelledby="events-heading">
        <div className="m2-card-header">
          <div>
            <h3 id="events-heading">Normalized events</h3>
            <p>Filter, search, and inspect redacted log records with source line provenance.</p>
          </div>
          <span className="m2-count-pill">{totalEvents.toLocaleString()} total</span>
        </div>

        <form
          className="m2-filter-bar"
          role="search"
          aria-label="Filter normalized events"
          onSubmit={(event) => {
            event.preventDefault();
            setSearchQuery(searchDraft.trim());
            setPage(1);
          }}
        >
          <div className="m2-filter-field">
            <label htmlFor="event-search">Search</label>
            <input
              id="event-search"
              type="search"
              maxLength={100}
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Message or service"
            />
          </div>
          <div className="m2-filter-field">
            <label htmlFor="event-severity">Severity</label>
            <select
              id="event-severity"
              value={severityFilter}
              onChange={(event) => {
                setSeverityFilter(event.target.value);
                setPage(1);
              }}
            >
              {SEVERITIES.map((item) => (
                <option key={item || "all"} value={item}>{item || "All severities"}</option>
              ))}
            </select>
          </div>
          <div className="m2-filter-field">
            <label htmlFor="event-source">Source</label>
            <select
              id="event-source"
              value={sourceFilter}
              onChange={(event) => {
                setSourceFilter(event.target.value);
                setPage(1);
              }}
            >
              <option value="">All sources</option>
              {sources.map((item) => (
                <option key={item.id} value={item.id}>{item.filename}</option>
              ))}
            </select>
          </div>
          <div className="m2-filter-field">
            <label htmlFor="event-sort">Sort</label>
            <select
              id="event-sort"
              value={sortOrder}
              onChange={(event) => {
                setSortOrder(event.target.value as EventSort);
                setPage(1);
              }}
            >
              <option value="latest">Latest occurred</option>
              <option value="earliest">Earliest occurred</option>
              <option value="source">Source &amp; line</option>
            </select>
          </div>
          <div className="m2-filter-field">
            <label htmlFor="event-zone">Timezone</label>
            <select
              id="event-zone"
              value={zone}
              onChange={(event) => setZone(event.target.value as DisplayTimezone)}
            >
              <option value="utc">UTC</option>
              <option value="local">Local</option>
            </select>
          </div>
          <div className="m2-filter-actions">
            <button className="button button-primary" type="submit">Apply</button>
            {(searchQuery || severityFilter || sourceFilter) && (
              <button
                className="button button-outline"
                type="button"
                onClick={() => {
                  setSearchDraft("");
                  setSearchQuery("");
                  setSeverityFilter("");
                  setSourceFilter("");
                  setPage(1);
                }}
              >
                Clear
              </button>
            )}
          </div>
        </form>

        {visibleEvents.length === 0 ? (
          <p className="m2-empty">No parsed events match the current filter.</p>
        ) : (
          <>
            <div className="m2-table-wrap">
              <table className="m2-table">
                <caption>Normalized incident log records</caption>
                <thead>
                  <tr>
                    <th scope="col">Timestamp</th>
                    <th scope="col">Severity</th>
                    <th scope="col">Service</th>
                    <th scope="col">Redacted message</th>
                    <th scope="col">Source lines</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleEvents.map((record) => {
                    const time = describeTime(record.occurred_at, record.timestamp_quality, zone);
                    return (
                      <tr key={record.id}>
                        <td className="m2-col-time">{time.valid ? `${time.date} ${time.clock}` : `${time.date} (${time.clock})`}</td>
                        <td>
                          {record.severity ? (
                            <span className={severityTone(record.severity)}>{record.severity}</span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="m2-col-service">{record.service || "—"}</td>
                        <td className="m2-col-message">{record.message}</td>
                        <td className="m2-col-lines">{formatLineRange(record.line_start, record.line_end)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="m1-pagination">
              <span>Page {page} · {totalEvents.toLocaleString()} total</span>
              <button type="button" disabled={!hasPrevious || page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                Previous
              </button>
              <button type="button" disabled={!hasNext} onClick={() => setPage((p) => p + 1)}>
                Next
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
