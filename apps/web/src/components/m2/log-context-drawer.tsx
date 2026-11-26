"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, describeApiFailure } from "@/lib/api-client";
import {
  describeTime,
  formatLineRange,
  type DisplayTimezone,
  type EvidenceEvent,
} from "@/lib/evidence-display";

type EventContextDetail = EvidenceEvent & {
  source_filename: string;
  source_sha256: string;
  parser_version: string;
};

type EventContextResponse = {
  event: EventContextDetail;
  before: EvidenceEvent[];
  after: EvidenceEvent[];
  window: number;
  related_trace_count: number;
  same_fingerprint_count: number;
};

function severityClass(severity: string): string {
  const s = (severity || "").toUpperCase();
  if (s === "ERROR" || s === "FATAL" || s === "CRITICAL") return "m2-sev m2-sev-error";
  if (s === "WARN" || s === "WARNING") return "m2-sev m2-sev-warn";
  if (s === "INFO" || s === "NOTICE") return "m2-sev m2-sev-info";
  return "m2-sev m2-sev-debug";
}

export function LogContextDrawer({
  incidentId,
  eventId,
  zone,
  onClose,
  onSelectEvent,
  onFilterTrace,
  onFilterFingerprint,
}: {
  incidentId: string;
  eventId: string;
  zone: DisplayTimezone;
  onClose: () => void;
  onSelectEvent: (nextId: string) => void;
  onFilterTrace: (traceId: string) => void;
  onFilterFingerprint: (fingerprint: string) => void;
}) {
  const [data, setData] = useState<EventContextResponse | null>(null);
  const [error, setError] = useState("");
  const [windowSize, setWindowSize] = useState(10);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    const encodedInc = encodeURIComponent(incidentId);
    const encodedEvt = encodeURIComponent(eventId);
    apiGet<EventContextResponse>(`incidents/${encodedInc}/events/${encodedEvt}/context?window=${windowSize}`)
      .then((res) => {
        if (active) {
          setData(res);
          setError("");
        }
      })
      .catch((failure: unknown) => {
        if (active) {
          setData(null);
          setError(describeApiFailure(failure));
        }
      });
    return () => {
      active = false;
    };
  }, [incidentId, eventId, windowSize]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  async function copyPayload(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard API may be unavailable in restricted contexts.
    }
  }

  const loading = data === null && !error;
  const activeEvent = data?.event;
  const timeInfo = activeEvent
    ? describeTime(activeEvent.occurred_at, activeEvent.timestamp_quality, zone)
    : null;

  return (
    <div
      className="drawer-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside className="drawer-panel" role="dialog" aria-modal="true" aria-label="Log event context">
        <header className="drawer-header">
          <div className="drawer-title-group">
            <span className="drawer-eyebrow">Log context inspector</span>
            <h2>{activeEvent ? activeEvent.source_filename : "Loading event…"}</h2>
          </div>
          <button
            type="button"
            className="drawer-close-btn"
            onClick={onClose}
            aria-label="Close context drawer"
          >
            ✕
          </button>
        </header>

        <div className="drawer-body">
          {loading && <p className="m1-hint" role="status">Loading surrounding source lines…</p>}
          {error && <p className="m1-error" role="alert">{error}</p>}

          {data && activeEvent && timeInfo && (
            <>
              <div className="drawer-badges-row">
                {activeEvent.severity && (
                  <span className={severityClass(activeEvent.severity)}>{activeEvent.severity}</span>
                )}
                {activeEvent.service && <span className="inc-ctx-chip">{activeEvent.service}</span>}
                <span className="inc-ctx-chip">
                  {formatLineRange(activeEvent.line_start, activeEvent.line_end)}
                </span>
                <span className="inc-ctx-age">
                  {timeInfo.valid ? `${timeInfo.date} ${timeInfo.clock}` : timeInfo.date}
                </span>
              </div>

              <section className="drawer-section" aria-label="Full log payload">
                <div className="drawer-section-head">
                  <h3>Redacted message</h3>
                  <button
                    type="button"
                    className="drawer-mini-btn"
                    onClick={() => void copyPayload(activeEvent.message)}
                  >
                    {copied ? "Copied" : "Copy payload"}
                  </button>
                </div>
                <pre className="drawer-payload">{activeEvent.message}</pre>
              </section>

              <dl className="drawer-meta-grid">
                <div>
                  <dt>Source file</dt>
                  <dd className="mono">{activeEvent.source_filename}</dd>
                </div>
                <div>
                  <dt>Source SHA-256</dt>
                  <dd className="mono" title={activeEvent.source_sha256}>
                    {activeEvent.source_sha256.slice(0, 16)}…
                  </dd>
                </div>
                <div>
                  <dt>Trace ID</dt>
                  <dd className="mono">{activeEvent.trace_id || "—"}</dd>
                </div>
                <div>
                  <dt>Fingerprint</dt>
                  <dd className="mono">{activeEvent.fingerprint || "—"}</dd>
                </div>
              </dl>

              <div className="drawer-actions-row">
                {activeEvent.trace_id && (
                  <button
                    type="button"
                    className="drawer-action-btn"
                    onClick={() => {
                      onFilterTrace(activeEvent.trace_id!);
                      onClose();
                    }}
                  >
                    Filter trace ({data.related_trace_count})
                  </button>
                )}
                {activeEvent.fingerprint && (
                  <button
                    type="button"
                    className="drawer-action-btn"
                    onClick={() => {
                      onFilterFingerprint(activeEvent.fingerprint!);
                      onClose();
                    }}
                  >
                    Same pattern ({data.same_fingerprint_count})
                  </button>
                )}
                <Link
                  className="drawer-action-btn"
                  href={`/incidents/${encodeURIComponent(incidentId)}/evidence-snapshots`}
                >
                  Open snapshots →
                </Link>
              </div>

              <section className="drawer-section" aria-label="Surrounding source lines">
                <div className="drawer-section-head">
                  <h3>Surrounding source context (±{windowSize} lines)</h3>
                  <div className="drawer-window-btns" role="group" aria-label="Context window size">
                    {[5, 10, 20].map((size) => (
                      <button
                        key={size}
                        type="button"
                        className={windowSize === size ? "drawer-mini-btn is-active" : "drawer-mini-btn"}
                        onClick={() => setWindowSize(size)}
                      >
                        ±{size}
                      </button>
                    ))}
                  </div>
                </div>

                <ol className="drawer-context-lines">
                  {data.before.map((row) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        className="drawer-ctx-line"
                        onClick={() => onSelectEvent(row.id)}
                      >
                        <span className="drawer-ctx-ln">{row.line_start}</span>
                        <span className="drawer-ctx-sev">{row.severity || "—"}</span>
                        <span className="drawer-ctx-msg">{row.message}</span>
                      </button>
                    </li>
                  ))}
                  <li className="drawer-ctx-line is-current" aria-current="true">
                    <span className="drawer-ctx-ln">{activeEvent.line_start}</span>
                    <span className="drawer-ctx-sev">{activeEvent.severity || "—"}</span>
                    <span className="drawer-ctx-msg">{activeEvent.message}</span>
                  </li>
                  {data.after.map((row) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        className="drawer-ctx-line"
                        onClick={() => onSelectEvent(row.id)}
                      >
                        <span className="drawer-ctx-ln">{row.line_start}</span>
                        <span className="drawer-ctx-sev">{row.severity || "—"}</span>
                        <span className="drawer-ctx-msg">{row.message}</span>
                      </button>
                    </li>
                  ))}
                </ol>
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
