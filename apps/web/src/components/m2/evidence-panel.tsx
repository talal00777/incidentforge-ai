"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAccount } from "@/components/m1/use-account";
import { LogContextDrawer } from "@/components/m2/log-context-drawer";
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
type FacetCount = { value: string; count: number };
type FingerprintFacet = {
  fingerprint: string;
  count: number;
  sample_message: string;
  severity: string;
  service: string;
};
type EventFacets = {
  total_events: number;
  severities: FacetCount[];
  services: FacetCount[];
  sources: { id: string; filename: string; count: number }[];
  top_fingerprints: FingerprintFacet[];
};

const ACTIVE_JOB_STATES = new Set(["queued", "running"]);

function severityTone(severity: string): string {
  const normalized = severity.toUpperCase();
  if (normalized === "ERROR" || normalized === "FATAL" || normalized === "CRITICAL") return "m2-sev m2-sev-error";
  if (normalized === "WARN" || normalized === "WARNING") return "m2-sev m2-sev-warn";
  if (normalized === "INFO" || normalized === "NOTICE") return "m2-sev m2-sev-info";
  return "m2-sev m2-sev-debug";
}

function rowSeverityEdge(severity: string): string {
  const normalized = severity.toUpperCase();
  if (normalized === "ERROR" || normalized === "FATAL" || normalized === "CRITICAL") return "log-row is-error";
  if (normalized === "WARN" || normalized === "WARNING") return "log-row is-warn";
  return "log-row";
}

function sourceStateTone(state: string): string {
  const normalized = state.toLowerCase();
  if (normalized === "completed" || normalized === "complete" || normalized === "parsed") {
    return "if-badge if-badge-resolved";
  }
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
  const [loaded, setLoaded] = useState(false);
  const [showUpload, setShowUpload] = useState<boolean | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [events, setEvents] = useState<EvidenceEvent[]>([]);
  const [facets, setFacets] = useState<EventFacets | null>(null);
  const [totalEvents, setTotalEvents] = useState(0);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrevious, setHasPrevious] = useState(false);
  const [severityFilter, setSeverityFilter] = useState("");
  const [serviceFilter, setServiceFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [traceFilter, setTraceFilter] = useState("");
  const [fingerprintFilter, setFingerprintFilter] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [regexMode, setRegexMode] = useState(false);
  const [sortOrder, setSortOrder] = useState<EventSort>("latest");
  const [zone, setZone] = useState<DisplayTimezone>("utc");
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [message, setMessage] = useState("");
  const [filterError, setFilterError] = useState("");
  const [busy, setBusy] = useState(false);

  const fetchEvidence = useCallback(async () => {
    const params = new URLSearchParams({ page: String(page), page_size: "50" });
    if (severityFilter) params.set("severity", severityFilter);
    if (serviceFilter) params.set("service", serviceFilter);
    if (sourceFilter) params.set("source_id", sourceFilter);
    if (traceFilter) params.set("trace_id", traceFilter);
    if (fingerprintFilter) params.set("fingerprint", fingerprintFilter);
    if (searchQuery) {
      params.set("search", searchQuery);
      if (regexMode) params.set("regex", "true");
    }
    params.set(
      "sort",
      sortOrder === "source" ? "source" : sortOrder === "earliest" ? "occurred_asc" : "occurred_desc",
    );
    const [nextSources, nextEvents, nextFacets] = await Promise.all([
      apiGet<Source[]>(`incidents/${encodedIncident}/sources`),
      apiGet<EventPage>(`incidents/${encodedIncident}/events?${params}`),
      apiGet<EventFacets>(`incidents/${encodedIncident}/events/facets`).catch(() => null),
    ]);
    return { nextSources, nextEvents, nextFacets };
  }, [
    encodedIncident,
    fingerprintFilter,
    page,
    regexMode,
    searchQuery,
    serviceFilter,
    severityFilter,
    sortOrder,
    sourceFilter,
    traceFilter,
  ]);

  const loadEvidence = useCallback(async () => {
    const { nextSources, nextEvents, nextFacets } = await fetchEvidence();
    setSources(nextSources);
    setEvents(nextEvents.results);
    setTotalEvents(nextEvents.count);
    setHasNext(nextEvents.next !== null);
    setHasPrevious(nextEvents.previous !== null);
    if (nextFacets) setFacets(nextFacets);
    setLoaded(true);
    setFilterError("");
  }, [fetchEvidence]);

  useEffect(() => {
    if (account.state !== "signed-in") return;
    let cancelled = false;
    fetchEvidence()
      .then(({ nextSources, nextEvents, nextFacets }) => {
        if (cancelled) return;
        setSources(nextSources);
        setEvents(nextEvents.results);
        setTotalEvents(nextEvents.count);
        setHasNext(nextEvents.next !== null);
        setHasPrevious(nextEvents.previous !== null);
        if (nextFacets) setFacets(nextFacets);
        setLoaded(true);
        setFilterError("");
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoaded(true);
          setFilterError(describeApiFailure(error));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [account.state, fetchEvidence]);

  useEffect(() => {
    if (account.state !== "signed-in" || !job || !ACTIVE_JOB_STATES.has(job.state)) return;
    let cancelled = false;
    const poll = window.setInterval(async () => {
      try {
        const next = await apiGet<Job>(`incidents/${encodedIncident}/jobs/${encodeURIComponent(job.id)}`);
        if (cancelled) return;
        setJob(next);
        if (!ACTIVE_JOB_STATES.has(next.state)) {
          await loadEvidence();
        }
      } catch (error) {
        if (!cancelled) setMessage(describeApiFailure(error));
      }
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(poll);
    };
  }, [account.state, encodedIncident, job, loadEvidence]);

  const visibleEvents = useMemo(
    () =>
      regexMode
        ? events
        : selectVisibleEvents(events, {
            query: searchQuery,
            severity: severityFilter,
            sourceId: sourceFilter,
            sort: sortOrder,
          }),
    [events, regexMode, searchQuery, severityFilter, sortOrder, sourceFilter],
  );

  const hasAnyFilter = Boolean(
    searchQuery || severityFilter || serviceFilter || sourceFilter || traceFilter || fingerprintFilter,
  );
  const uploadOpen = showUpload ?? (loaded && sources.length === 0);

  function clearAllFilters() {
    setSearchDraft("");
    setSearchQuery("");
    setRegexMode(false);
    setSeverityFilter("");
    setServiceFilter("");
    setSourceFilter("");
    setTraceFilter("");
    setFingerprintFilter("");
    setPage(1);
  }

  if (account.state === "loading") {
    return (
      <div className="m2-panel">
        <header className="stage-toolbar"><h1 className="stage-title">Incident evidence</h1></header>
        <p role="status">Checking your session…</p>
      </div>
    );
  }
  if (account.state === "error") {
    return (
      <div className="m2-panel">
        <header className="stage-toolbar"><h1 className="stage-title">Incident evidence</h1></header>
        <p role="alert" className="m1-error">{account.message}</p>
      </div>
    );
  }
  if (account.state === "signed-out") {
    return (
      <div className="m2-panel">
        <header className="stage-toolbar"><h1 className="stage-title">Incident evidence</h1></header>
        <section className="panel m1-prompt">
          <p>
            Please <Link href="/login">sign in</Link> to upload and inspect evidence.
          </p>
        </section>
      </div>
    );
  }

  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (files.length < 1 || files.length > 5) return;
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
      setShowUpload(false);
      setMessage("Upload accepted. Processing in background worker.");
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
      <header className="stage-toolbar">
        <div className="stage-toolbar-left">
          <h1 className="stage-title">Incident evidence</h1>
          <span className="inc-ctx-age">{totalEvents.toLocaleString()} events</span>
        </div>
        <div className="stage-toolbar-controls">
          <button
            type="button"
            className={showSources ? "quiet-btn is-active" : "quiet-btn"}
            aria-expanded={showSources}
            onClick={() => setShowSources((cur) => !cur)}
          >
            Sources ({sources.length})
          </button>
          <button
            type="button"
            className={uploadOpen ? "quiet-btn is-active" : "quiet-btn is-accent"}
            aria-expanded={uploadOpen}
            onClick={() => setShowUpload(!uploadOpen)}
          >
            {uploadOpen ? "Hide upload" : "+ Upload logs"}
          </button>
        </div>
      </header>

      {(message || job) && (
        <div className="m2-status-banner" role="status" aria-live="polite">
          <span>
            {job ? (
              <>
                <strong>Ingestion job:</strong> {job.state} · {job.accepted} accepted, {job.rejected} rejected
                {job.error_code ? ` (${job.error_code})` : ""}
              </>
            ) : (
              message
            )}
          </span>
          {job && (
            <button className="quiet-btn" type="button" onClick={() => void checkJob()}>
              Refresh
            </button>
          )}
        </div>
      )}

      {uploadOpen && (
        <section className="m2-card" aria-labelledby="evidence-heading">
          <div className="m2-card-body">
            <h2 id="evidence-heading" className="sr-only">Upload log files</h2>
            <form className="m2-upload-form" onSubmit={upload}>
              <div className="m2-file-field">
                <label htmlFor="log-files">Log files (.log, .txt, .jsonl, .json · up to 5 files, 25 MiB each)</label>
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
          </div>
        </section>
      )}

      {showSources && (
        <section className="m2-card" aria-labelledby="sources-heading">
          <div className="m2-card-header">
            <h2 id="sources-heading" style={{ fontSize: "14px" }}>Uploaded sources</h2>
            <span className="inc-ctx-age">{sources.length} {sources.length === 1 ? "file" : "files"}</span>
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
                      <span>·</span>
                      <span>{source.rejected.toLocaleString()} rejected</span>
                      <span>·</span>
                      <span className="mono" title={source.sha256}>sha256:{source.sha256.slice(0, 12)}</span>
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
      )}

      <section className="m2-card" aria-labelledby="events-heading">
        <h2 id="events-heading" className="sr-only">Log explorer</h2>
        <form
          className="log-toolbar"
          role="search"
          aria-label="Filter normalized events"
          onSubmit={(event) => {
            event.preventDefault();
            setSearchQuery(searchDraft.trim());
            setPage(1);
          }}
        >
          <div className="log-search-combo">
            <label htmlFor="event-search" className="sr-only">
              Search {regexMode ? "(Regex)" : "(Text)"}
            </label>
            <input
              id="event-search"
              type="search"
              maxLength={regexMode ? 80 : 100}
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder={regexMode ? "Regex e.g. PoolTimeout.*503" : "Search messages, services, or trace IDs…"}
            />
            <button
              type="button"
              className={regexMode ? "log-regex-btn is-active" : "log-regex-btn"}
              aria-pressed={regexMode}
              title="Toggle regular expression search"
              onClick={() => {
                setRegexMode((cur) => !cur);
                setPage(1);
              }}
            >
              .*
            </button>
          </div>

          {sources.length > 1 && (
            <>
              <label htmlFor="event-source" className="sr-only">Source file</label>
              <select
                id="event-source"
                className="log-compact-select"
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
            </>
          )}

          <label htmlFor="event-sort" className="sr-only">Sort order</label>
          <select
            id="event-sort"
            className="log-compact-select"
            value={sortOrder}
            onChange={(event) => {
              setSortOrder(event.target.value as EventSort);
              setPage(1);
            }}
          >
            <option value="latest">Latest first</option>
            <option value="earliest">Earliest first</option>
            <option value="source">Source line</option>
          </select>

          <div className="dash-filter-tabs" role="group" aria-label="Display timezone">
            <button
              type="button"
              aria-pressed={zone === "utc"}
              className={zone === "utc" ? "dash-filter-tab is-active" : "dash-filter-tab"}
              onClick={() => setZone("utc")}
            >
              UTC
            </button>
            <button
              type="button"
              aria-pressed={zone === "local"}
              className={zone === "local" ? "dash-filter-tab is-active" : "dash-filter-tab"}
              onClick={() => setZone("local")}
            >
              Local
            </button>
          </div>

          <button className="demo-launch-btn" type="submit">Apply</button>
          {hasAnyFilter && (
            <button className="quiet-btn" type="button" onClick={clearAllFilters}>
              Clear
            </button>
          )}
        </form>

        {facets && facets.total_events > 0 && (
          <div className="log-facets-strip" aria-label="Quick log facets">
            <div className="log-facet-chips" role="group" aria-label="Filter by severity">
              {facets.severities.map((item) => {
                const active = severityFilter === item.value;
                return (
                  <button
                    key={item.value}
                    type="button"
                    className={active ? "log-facet-chip is-active" : "log-facet-chip"}
                    aria-pressed={active}
                    onClick={() => {
                      setSeverityFilter(active ? "" : item.value);
                      setPage(1);
                    }}
                  >
                    <span>{item.value}</span>
                    <strong>{item.count}</strong>
                  </button>
                );
              })}
            </div>

            {facets.services.length > 0 && (
              <>
                <span className="log-facet-divider" aria-hidden="true" />
                <div className="log-facet-chips" role="group" aria-label="Filter by service">
                  {facets.services.slice(0, 6).map((item) => {
                    const active = serviceFilter === item.value;
                    return (
                      <button
                        key={item.value}
                        type="button"
                        className={active ? "log-facet-chip is-active" : "log-facet-chip"}
                        aria-pressed={active}
                        onClick={() => {
                          setServiceFilter(active ? "" : item.value);
                          setPage(1);
                        }}
                      >
                        <span className="mono">{item.value}</span>
                        <strong>{item.count}</strong>
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        )}

        {(traceFilter || fingerprintFilter) && (
          <div className="log-active-pills" aria-label="Active query constraints">
            {traceFilter && (
              <span className="log-active-pill">
                trace: <code>{traceFilter}</code>
                <button type="button" aria-label="Remove trace filter" onClick={() => { setTraceFilter(""); setPage(1); }}>×</button>
              </span>
            )}
            {fingerprintFilter && (
              <span className="log-active-pill">
                pattern: <code>{fingerprintFilter.slice(0, 14)}</code>
                <button type="button" aria-label="Remove pattern filter" onClick={() => { setFingerprintFilter(""); setPage(1); }}>×</button>
              </span>
            )}
          </div>
        )}

        {filterError && (
          <div style={{ padding: "12px 20px 0" }}>
            <p className="m1-error" role="alert" style={{ margin: 0 }}>{filterError}</p>
          </div>
        )}

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
                    <th scope="col">Level</th>
                    <th scope="col">Service</th>
                    <th scope="col">Message</th>
                    <th scope="col">Line</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleEvents.map((record) => {
                    const time = describeTime(record.occurred_at, record.timestamp_quality, zone);
                    return (
                      <tr
                        key={record.id}
                        className={rowSeverityEdge(record.severity)}
                        onClick={() => setSelectedEventId(record.id)}
                      >
                        <td className="m2-col-time">{time.valid ? `${time.date} ${time.clock}` : `${time.date} (${time.clock})`}</td>
                        <td>
                          {record.severity ? (
                            <span className={severityTone(record.severity)}>{record.severity}</span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="m2-col-service">{record.service || "—"}</td>
                        <td className="m2-col-message">
                          <div className="log-msg-cell">
                            <span>{record.message}</span>
                            {record.trace_id && (
                              <span className="log-trace-inline">trace:{record.trace_id}</span>
                            )}
                          </div>
                        </td>
                        <td className="m2-col-lines">
                          <button
                            type="button"
                            className="log-inspect-link"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedEventId(record.id);
                            }}
                          >
                            {formatLineRange(record.line_start, record.line_end)} →
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="m1-pagination">
              <span>Page {page} · {totalEvents.toLocaleString()} events</span>
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

      {selectedEventId && (
        <LogContextDrawer
          incidentId={incidentId}
          eventId={selectedEventId}
          zone={zone}
          onClose={() => setSelectedEventId(null)}
          onSelectEvent={(nextId) => setSelectedEventId(nextId)}
          onFilterTrace={(traceId) => {
            setTraceFilter(traceId);
            setPage(1);
          }}
          onFilterFingerprint={(fp) => {
            setFingerprintFilter(fp);
            setPage(1);
          }}
        />
      )}
    </div>
  );
}
