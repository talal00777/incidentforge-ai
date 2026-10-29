"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiGet, describeApiFailure } from "@/lib/api-client";
import styles from "./relationships.module.css";

type Zone = "utc" | "local";
type RelatedEvent = {
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
type Group = {
  key: string;
  kind: "trace" | "request";
  event_count: number;
  service_count: number;
  services: string[];
  first_at: string | null;
  last_at: string | null;
  unknown_time: number;
  truncated: boolean;
  events: RelatedEvent[];
};
type Transition = {
  from_service: string;
  to_service: string;
  count: number;
  event_ids: string[];
};
type Relationships = {
  total_events: number;
  correlated_groups: number;
  unknown_time: number;
  groups: Group[];
  transitions: Transition[];
  timeline: RelatedEvent[];
  timeline_truncated: boolean;
};

function eventTime(value: string | null, zone: Zone): string {
  if (!value) return "Time unknown";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Time unknown";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    second: "2-digit", hour12: false, timeZone: zone === "utc" ? "UTC" : undefined,
  }).format(date) + (zone === "utc" ? " UTC" : " local");
}

function EventList({ events, zone, incidentId }: { events: RelatedEvent[]; zone: Zone; incidentId: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <ol className={styles.eventList}>
      {events.map((event) => (
        <li className={styles.eventRow} key={event.id}>
          <button
            type="button" className={styles.eventButton} onClick={() => setSelected(selected === event.id ? null : event.id)}
            aria-expanded={selected === event.id}
          >
            <span className={styles.eventTime}><time dateTime={event.occurred_at ?? undefined}>{eventTime(event.occurred_at, zone)}</time></span>
            <span className={`${styles.severity} ${["ERROR", "FATAL", "CRITICAL"].includes(event.severity) ? styles.error : ""}`}>{event.severity || "UNKNOWN"}</span>
            <span className={styles.eventService}>{event.service || "Unknown service"}</span>
            <span className={styles.eventMessage}>{event.message || "No message"}</span>
            <span className={styles.expandIcon} aria-hidden="true">{selected === event.id ? "−" : "+"}</span>
          </button>
          {selected === event.id && (
            <div className={styles.eventDetail}>
              <div><span>Source lines</span><strong>{event.line_start === event.line_end ? event.line_start : `${event.line_start}–${event.line_end}`}</strong></div>
              <div><span>Timestamp</span><strong>{event.timestamp_quality.replaceAll("_", " ")}</strong></div>
              <p>{event.message}</p>
              <Link href={`/incidents/${encodeURIComponent(incidentId)}/sources`}>Open evidence</Link>
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

export function RelationshipsPanel({ incidentId }: { incidentId: string }) {
  const [data, setData] = useState<Relationships | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [zone, setZone] = useState<Zone>("utc");
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [selectedTransition, setSelectedTransition] = useState<number | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let alive = true;
    apiGet<Relationships>(`incidents/${encodeURIComponent(incidentId)}/relationships`)
      .then((result) => { if (alive) { setData(result); setError(""); } })
      .catch((failure) => { if (alive) setError(describeApiFailure(failure)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [incidentId]);

  const activeGroup = data?.groups.find((g) => g.key === selectedGroup) ?? null;
  const transition = selectedTransition === null ? null : data?.transitions[selectedTransition];
  const transitionEvents = useMemo(() => {
    if (!transition || !data) return [];
    return data.timeline.filter((event) => transition.event_ids.includes(event.id));
  }, [transition, data]);

  return (
    <main className={styles.root} aria-busy={loading}>
      <header className={styles.header}>
        <h1>Event relationships</h1>
        <div className={styles.actions}>
          <div role="group" aria-label="Display timezone" className={styles.zone}>
            <button type="button" aria-pressed={zone === "utc"} onClick={() => setZone("utc")}>UTC</button>
            <button type="button" aria-pressed={zone === "local"} onClick={() => setZone("local")}>Local</button>
          </div>
          <Link className={styles.back} href={`/incidents/${encodeURIComponent(incidentId)}/evidence-snapshots`}>Evidence selection</Link>
          <Link className={styles.back} href={`/incidents/${encodeURIComponent(incidentId)}/analysis`}>Incident analysis</Link>
        </div>
      </header>

      {loading && <p role="status" className={styles.state}>Loading relationships…</p>}
      {error && <p role="alert" className={styles.errorBox}>{error}</p>}
      {!loading && !error && data && (
        <>
          <section className={styles.metrics} aria-label="Relationship totals">
            <div><span>Events</span><strong>{data.total_events.toLocaleString()}</strong></div>
            <div><span>Linked groups</span><strong>{data.correlated_groups.toLocaleString()}</strong></div>
            <div><span>Service transitions</span><strong>{data.transitions.length.toLocaleString()}</strong></div>
            <div><span>Unknown time</span><strong>{data.unknown_time.toLocaleString()}</strong></div>
          </section>

          <div className={styles.grid}>
            <section className={styles.card} aria-labelledby="relationship-groups">
              <div className={styles.cardHeading}><h2 id="relationship-groups">Shared identifiers</h2><span>{data.groups.length}</span></div>
              {data.groups.length === 0 ? <p className={styles.empty}>No shared trace or request IDs</p> : (
                <div className={styles.groupList} role="group" aria-label="Linked event groups">
                  {data.groups.map((group, index) => (
                    <button key={group.key} type="button" className={`${styles.groupButton} ${selectedGroup === group.key ? styles.selected : ""}`}
                      aria-pressed={selectedGroup === group.key} onClick={() => { setSelectedGroup(group.key === selectedGroup ? null : group.key); setSelectedTransition(null); }}>
                      <span className={styles.groupTitle}>{group.kind === "trace" ? "Trace" : "Request"} {index + 1}</span>
                      <span className={styles.groupMeta}>{group.event_count} events · {group.service_count} services</span>
                      <span className={styles.groupServices}>{group.services.join(" · ") || "Unknown service"}</span>
                    </button>
                  ))}
                </div>
              )}
            </section>
            <section className={styles.card} aria-labelledby="service-transitions">
              <div className={styles.cardHeading}><h2 id="service-transitions">Observed service order</h2><span>{data.transitions.length}</span></div>
              {data.transitions.length === 0 ? <p className={styles.empty}>No cross-service transitions in linked events</p> : (
                <div className={styles.transitionList} role="group" aria-label="Service transitions">
                  {data.transitions.map((edge, index) => (
                    <button className={`${styles.transitionButton} ${selectedTransition === index ? styles.selected : ""}`} type="button" key={`${edge.from_service}-${edge.to_service}`}
                      aria-pressed={selectedTransition === index} onClick={() => { setSelectedTransition(selectedTransition === index ? null : index); setSelectedGroup(null); }}>
                      <span>{edge.from_service}<span className={styles.arrow} aria-hidden="true">→</span>{edge.to_service}</span>
                      <strong>{edge.count}</strong>
                    </button>
                  ))}
                </div>
              )}
            </section>
          </div>

          <section className={styles.card} aria-labelledby="relationship-timeline">
            <div className={styles.cardHeading}>
              <h2 id="relationship-timeline">{activeGroup ? "Linked events" : transition ? "Transition evidence" : "Event timeline"}</h2>
              {(activeGroup || transition) && <button className={styles.clear} type="button" onClick={() => { setSelectedGroup(null); setSelectedTransition(null); }}>Clear selection</button>}
            </div>
            {activeGroup ? (
              <><EventList key={activeGroup.key} events={activeGroup.events} zone={zone} incidentId={incidentId} />{activeGroup.truncated && <p className={styles.more}>First 30 linked events shown</p>}</>
            ) : transition ? (
              transitionEvents.length ? <EventList key={selectedTransition} events={transitionEvents} zone={zone} incidentId={incidentId} /> : <p className={styles.empty}>Evidence is outside the current timeline sample</p>
            ) : data.timeline.length ? (
              <><EventList key="timeline" events={showAll ? data.timeline : data.timeline.slice(0, 15)} zone={zone} incidentId={incidentId} />
              {data.timeline.length > 15 && <button className={styles.moreButton} type="button" onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show ${data.timeline.length - 15} more`}</button>}
              {data.timeline_truncated && <p className={styles.more}>Recent timed events and a limited unknown-time sample</p>}</>
            ) : <p className={styles.empty}>No events available</p>}
          </section>
        </>
      )}
    </main>
  );
}
