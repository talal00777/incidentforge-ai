"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiGet, apiWrite, describeApiFailure } from "@/lib/api-client";
import { evidenceTime, MAX_SELECTED_EVENTS, selectionKey, toggleEvidenceSelection } from "@/lib/evidence-selection";
import styles from "./evidence-snapshots.module.css";

type Zone = "utc" | "local";
type IncidentEvent = {
  id: string;
  source_id: string;
  line_start: number;
  line_end: number;
  occurred_at: string | null;
  timestamp_quality: string;
  severity: string;
  service: string;
  message: string;
};
type EventPage = {
  count: number;
  next: string | null;
  results: IncidentEvent[];
};
type EvidenceEntry = {
  event_id: string;
  source_id: string;
  source_sha256: string;
  source_name: string;
  source_lines: [number, number];
  occurred_at: string | null;
  timestamp_quality: string;
  severity: string;
  service: string;
  message: string;
};
type EvidencePreview = {
  sha256: string;
  event_count: number;
  characters: number;
  payload_bytes: number;
  privacy_policy_version: string;
  entries: EvidenceEntry[];
  transmitted: boolean;
};
type EvidenceSnapshot = EvidencePreview & {
  id: string;
  consent_accepted_at: string;
  created_at: string;
};
type SnapshotSummary = Omit<EvidenceSnapshot, "entries">;

function sourceLines(entry: EvidenceEntry): string {
  const [start, end] = entry.source_lines;
  return start === end ? `Line ${start}` : `Lines ${start}–${end}`;
}

function EvidencePreviewList({ entries, zone }: { entries: EvidenceEntry[]; zone: Zone }) {
  return (
    <ol className={styles.previewList}>
      {entries.map((entry) => (
        <li key={entry.event_id} className={styles.previewEvent}>
          <div className={styles.previewEventMeta}>
            <time dateTime={entry.occurred_at ?? undefined}>{evidenceTime(entry.occurred_at, zone)}</time>
            <span>{entry.severity || "UNKNOWN"}</span>
            <span>{entry.service || "Unknown service"}</span>
            <span>{entry.source_name} · {sourceLines(entry)}</span>
          </div>
          <p>{entry.message || "No message"}</p>
        </li>
      ))}
    </ol>
  );
}

export function EvidenceSnapshotsPanel({ incidentId }: { incidentId: string }) {
  const [events, setEvents] = useState<IncidentEvent[]>([]);
  const [eventPage, setEventPage] = useState(1);
  const [nextPage, setNextPage] = useState(false);
  const [totalEvents, setTotalEvents] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [preview, setPreview] = useState<EvidencePreview | null>(null);
  const [previewKey, setPreviewKey] = useState("");
  const [consented, setConsented] = useState(false);
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [saved, setSaved] = useState<EvidenceSnapshot | null>(null);
  const [openSnapshot, setOpenSnapshot] = useState<EvidenceSnapshot | null>(null);
  const [zone, setZone] = useState<Zone>("utc");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  const basePath = `incidents/${encodeURIComponent(incidentId)}/evidence`;
  const currentKey = useMemo(() => selectionKey(selected), [selected]);
  const activePreview = preview !== null && previewKey === currentKey ? preview : null;

  const loadEvents = useCallback(async (page: number) => {
    const result = await apiGet<EventPage>(`incidents/${encodeURIComponent(incidentId)}/events?page_size=50&page=${page}`);
    setEvents((existing) => page === 1 ? result.results : [...existing, ...result.results]);
    setEventPage(page);
    setTotalEvents(result.count);
    setNextPage(result.next !== null);
  }, [incidentId]);

  const loadSnapshots = useCallback(async () => {
    setSnapshots(await apiGet<SnapshotSummary[]>(`${basePath}/snapshots`));
  }, [basePath]);

  useEffect(() => {
    let active = true;
    Promise.all([loadEvents(1), loadSnapshots()])
      .catch((failure) => { if (active) setError(describeApiFailure(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [loadEvents, loadSnapshots]);

  function toggle(id: string) {
    setSelected((current) => toggleEvidenceSelection(current, id));
    setPreview(null);
    setConsented(false);
    setSaved(null);
    setError("");
  }

  async function requestPreview() {
    if (!selected.length) return;
    setWorking(true);
    setError("");
    setPreview(null);
    setConsented(false);
    try {
      const result = await apiWrite<EvidencePreview>(`${basePath}/preview`, "POST", { event_ids: selected });
      setPreview(result);
      setPreviewKey(currentKey);
    } catch (failure) {
      setError(describeApiFailure(failure));
    } finally {
      setWorking(false);
    }
  }

  async function saveSnapshot() {
    if (!activePreview || !consented || working) return;
    setWorking(true);
    setError("");
    try {
      const result = await apiWrite<EvidenceSnapshot>(`${basePath}/snapshots`, "POST", {
        event_ids: selected,
        expected_sha256: activePreview.sha256,
        privacy_consent: { accepted: true, policy_version: activePreview.privacy_policy_version },
      });
      // A new preview is mandatory after a selection change; saving never starts an AI call.
      setSaved(result);
      setConsented(false);
      await loadSnapshots();
    } catch (failure) {
      setError(describeApiFailure(failure));
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className={styles.root}>
      <header className={styles.header}>
        <h1>Evidence selection</h1>
        <div className={styles.headerActions}>
          <div className={styles.zone} role="group" aria-label="Display timezone">
            <button type="button" aria-pressed={zone === "utc"} onClick={() => setZone("utc")}>UTC</button>
            <button type="button" aria-pressed={zone === "local"} onClick={() => setZone("local")}>Local</button>
          </div>
          <Link className={styles.secondaryLink} href={`/incidents/${encodeURIComponent(incidentId)}/relationships`}>Relationships</Link>
        </div>
      </header>

      {error && <p className={styles.error} role="alert">{error}</p>}
      {loading ? <p className={styles.state} role="status">Loading evidence…</p> : (
        <div className={styles.columns}>
          <section className={styles.card} aria-labelledby="selection-heading">
            <div className={styles.cardHeader}>
              <h2 id="selection-heading">Incident events</h2>
              <span>{selected.length}/{MAX_SELECTED_EVENTS} selected · {totalEvents} total</span>
            </div>
            {events.length === 0 ? (
              <p className={styles.state}>No events available</p>
            ) : (
              <div className={styles.eventList} role="group" aria-label="Select incident events">
                {events.map((item) => (
                  <label className={styles.selectEvent} key={item.id}>
                    <input type="checkbox" checked={selected.includes(item.id)}
                      disabled={working || (!selected.includes(item.id) && selected.length >= MAX_SELECTED_EVENTS)}
                      onChange={() => toggle(item.id)} />
                    <span className={styles.eventText}>
                      <span className={styles.eventMeta}>
                        <time dateTime={item.occurred_at ?? undefined}>{evidenceTime(item.occurred_at, zone)}</time>
                        <strong>{item.severity || "UNKNOWN"}</strong>
                        <span>{item.service || "Unknown service"}</span>
                      </span>
                      <span className={styles.message}>{item.message || "No message"}</span>
                    </span>
                  </label>
                ))}
              </div>
            )}
            <div className={styles.footer}>
              {nextPage && <button type="button" className={styles.secondaryButton} disabled={working} onClick={async () => {
                setWorking(true);
                setError("");
                try { await loadEvents(eventPage + 1); }
                catch (failure) { setError(describeApiFailure(failure)); }
                finally { setWorking(false); }
              }}>Load more</button>}
              <button type="button" className={styles.primaryButton} disabled={working || !selected.length} onClick={() => void requestPreview()}>Preview selected evidence</button>
            </div>
          </section>

          <div className={styles.rightColumn}>
            <section className={styles.card} aria-labelledby="preview-heading">
              <div className={styles.cardHeader}>
                <h2 id="preview-heading">Transfer preview</h2>
                {activePreview && <span>{activePreview.event_count} events · {(activePreview.payload_bytes / 1024).toFixed(1)} KB</span>}
              </div>
              {activePreview ? (
                <>
                  <div className={styles.previewScroll}><EvidencePreviewList entries={activePreview.entries} zone={zone} /></div>
                  <div className={styles.consentSection}>
                    <label className={styles.consentLabel}>
                      <input type="checkbox" checked={consented} disabled={working || saved !== null}
                        onChange={(event) => setConsented(event.target.checked)} />
                      <span>I approve preparing this redacted evidence for external AI analysis. No data will be sent now.</span>
                    </label>
                    <button className={styles.primaryButton} type="button" onClick={() => void saveSnapshot()}
                      disabled={!consented || working || saved !== null}>
                      {saved ? "Snapshot saved" : "Save evidence snapshot"}
                    </button>
                  </div>
                  {saved && <p role="status" className={styles.saved}>Saved locally · {saved.event_count} events · {evidenceTime(saved.created_at, zone)}</p>}
                </>
              ) : <p className={styles.state}>Select events to preview</p>}
            </section>

            <section className={styles.card} aria-labelledby="snapshot-heading">
              <div className={styles.cardHeader}><h2 id="snapshot-heading">Saved snapshots</h2><span>{snapshots.length}</span></div>
              {snapshots.length ? (
                <ul className={styles.snapshotList}>
                  {snapshots.map((snapshot) => (
                    <li key={snapshot.id}>
                      <span>{snapshot.event_count} events</span>
                      <time dateTime={snapshot.created_at}>{evidenceTime(snapshot.created_at, zone)}</time>
                      <button type="button" className={styles.secondaryButton} disabled={working} onClick={async () => {
                        setWorking(true);
                        setError("");
                        try { setOpenSnapshot(await apiGet<EvidenceSnapshot>(`${basePath}/snapshots/${encodeURIComponent(snapshot.id)}`)); }
                        catch (failure) { setError(describeApiFailure(failure)); }
                        finally { setWorking(false); }
                      }}>View</button>
                    </li>
                  ))}
                </ul>
              ) : <p className={styles.state}>No saved snapshots</p>}
              {openSnapshot && <div className={styles.openSnapshot}>
                <div className={styles.openSnapshotHeader}>
                  <strong>{openSnapshot.event_count} selected events</strong>
                  <button className={styles.secondaryButton} type="button" onClick={() => setOpenSnapshot(null)}>Close</button>
                </div>
                <EvidencePreviewList entries={openSnapshot.entries} zone={zone} />
              </div>}
            </section>
          </div>
        </div>
      )}
    </main>
  );
}
