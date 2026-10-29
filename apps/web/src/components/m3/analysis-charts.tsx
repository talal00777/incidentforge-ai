"use client";

import { useMemo, useState } from "react";

import { timePositionPercent, timelineColumnWidth, timelineCountTicks } from "@/lib/analysis-timeline";
import {
  chartPage,
  chartPages,
  eventTimeLabel,
  orderedTimeline,
  safePercent,
  type IncidentAnalysis,
} from "@/lib/analysis-display";

import styles from "./incident-analysis.module.css";

type Timezone = "utc" | "local";
type ChartRow = { key: string; label: string; count: number; color: string };

const severityColors: Record<string, string> = {
  DEBUG: "#94a3b8",
  INFO: "#568bbb",
  NOTICE: "#6479b8",
  WARN: "#d19b4a",
  WARNING: "#d19b4a",
  ERROR: "#d36d66",
  FATAL: "#a85168",
  CRITICAL: "#a85168",
};

function HorizontalChart({ title, rows, empty }: { title: string; rows: ChartRow[]; empty: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  const maximum = Math.max(0, ...rows.map((row) => row.count));
  const active = rows.find((row) => row.key === selected);

  return (
    <section className={`${styles.card} ${styles.comparison}`} aria-label={title}>
      <header className={styles.cardHeader}>
        <h3>{title}</h3>
        <span className={styles.unit}>Events</span>
      </header>
      {rows.length === 0 ? <p className={styles.empty}>{empty}</p> : (
        <>
          <div className={styles.barsList} role="group" aria-label={`${title} values`}>
            {rows.map((row) => (
              <button
                type="button"
                key={row.key}
                className={`${styles.barRow} ${selected === row.key ? styles.barActive : ""}`}
                aria-label={`${row.label}: ${row.count.toLocaleString()} events`}
                aria-pressed={selected === row.key}
                title={row.label}
                onClick={() => setSelected(selected === row.key ? null : row.key)}
              >
                <span className={styles.barName}>{row.label}</span>
                <span className={styles.barTrack} aria-hidden="true">
                  <span className={styles.barFill} style={{ width: `${safePercent(row.count, maximum)}%`, backgroundColor: row.color }} />
                </span>
                <strong className={styles.barValue}>{row.count.toLocaleString()}</strong>
              </button>
            ))}
          </div>
          {active && <div className={styles.selection} role="status"><span>{active.label}</span><strong>{active.count.toLocaleString()} events</strong></div>}
        </>
      )}
    </section>
  );
}

function TimelineChart({ data, bucket, zone }: { data: IncidentAnalysis; bucket: string; zone: Timezone }) {
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const ordered = useMemo(() => orderedTimeline(data.timeline), [data.timeline]);
  const lastPage = chartPages(ordered.length) - 1;
  const currentPage = Math.min(page, lastPage);
  const visible = chartPage(ordered, currentPage);
  const maximum = Math.max(1, ...visible.map((item) => item.total));
  const countTicks = timelineCountTicks(maximum);
  const first = visible[0]?.start ?? "";
  const last = visible[visible.length - 1]?.start ?? "";
  const columnWidth = timelineColumnWidth(visible);
  const chosen = visible.find((item) => item.start === selected);
  const flagged = new Set(data.anomaly.buckets);
  const hasBaseline = data.anomaly.status !== "insufficient_data";

  return (
    <section className={styles.card} aria-labelledby="if-timeline-title">
      <header className={styles.cardHeader}>
        <h3 id="if-timeline-title">Event timeline</h3>
        <div className={styles.timelineMeta}>
          <span className={styles.unit}>{bucket}-min buckets · {zone === "utc" ? "UTC" : "Local"}</span>
          <span className={styles.stateLabel}>{hasBaseline ? `${data.anomaly.buckets.length.toLocaleString()} flagged` : "No baseline"}</span>
        </div>
      </header>
      {ordered.length === 0 ? <p className={styles.empty}>No timed events</p> : (
        <>
          <div className={styles.timelineVisual}>
            <div className={styles.yAxis} aria-hidden="true">
              {countTicks.map((tick) => <span key={tick} style={{ bottom: `${safePercent(tick, maximum)}%` }}>{tick}</span>)}
            </div>
            <div className={styles.plotArea}>
              <div className={styles.plot} role="group" aria-label="Observed event counts by time">
                <div className={styles.gridlines} aria-hidden="true">
                  {countTicks.map((tick) => <span key={tick} style={{ bottom: `${safePercent(tick, maximum)}%` }} />)}
                </div>
                {visible.map((item) => {
                  const active = selected === item.start;
                  const position = timePositionPercent(item.start, first, last);
                  const edgeOffset = (0.5 - position / 100) * columnWidth;
                  return (
                    <button
                      type="button"
                      key={item.start}
                      className={`${styles.timelineColumn} ${active ? styles.timelineActive : ""} ${flagged.has(item.start) ? styles.timelineFlagged : ""}`}
                      style={{ left: `calc(${position}% + ${edgeOffset}px)`, width: `${columnWidth}px` }}
                      aria-pressed={active}
                      aria-label={`${eventTimeLabel(item.start, zone)}: ${item.total} events, ${item.errors} error-level`}
                      title={`${eventTimeLabel(item.start, zone)} · ${item.total} events · ${item.errors} errors`}
                      onClick={() => setSelected(active ? null : item.start)}
                    >
                      <span className={styles.columnStack} aria-hidden="true" style={{ height: `${Math.max(3, safePercent(item.total, maximum))}%` }}>
                        <span className={styles.columnErrors} style={{ height: `${safePercent(item.errors, item.total)}%` }} />
                      </span>
                    </button>
                  );
                })}
              </div>
              <div className={styles.xAxis}>
                <time dateTime={first}>{eventTimeLabel(first, zone)}</time>
                {first !== last && (
                  <>
                    <span className={styles.midTick}>{eventTimeLabel(new Date((Date.parse(first) + Date.parse(last)) / 2).toISOString(), zone)}</span>
                    <time dateTime={last}>{eventTimeLabel(last, zone)}</time>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className={styles.chartFooter}>
            <div className={styles.legend} aria-label="Chart legend">
              <span><i className={styles.legendOther} /> Other events</span>
              <span><i className={styles.legendError} /> Error-level</span>
              {data.missing_event_time > 0 && <span className={styles.missingTime}>{data.missing_event_time.toLocaleString()} unknown time</span>}
            </div>
            {lastPage > 0 && (
              <div className={styles.pager}>
                <button type="button" disabled={currentPage === 0} onClick={() => { setPage(currentPage - 1); setSelected(null); }}>Previous</button>
                <span>{currentPage + 1} / {lastPage + 1}</span>
                <button type="button" disabled={currentPage === lastPage} onClick={() => { setPage(currentPage + 1); setSelected(null); }}>Next</button>
              </div>
            )}
          </div>
          {chosen && <div className={styles.selection} role="status"><span>{eventTimeLabel(chosen.start, zone)}</span><strong>{chosen.total.toLocaleString()} events · {chosen.errors.toLocaleString()} errors</strong></div>}
        </>
      )}
    </section>
  );
}

export function AnalysisCharts({ data, bucket, zone }: { data: IncidentAnalysis; bucket: string; zone: Timezone }) {
  const severity = data.severity_counts.filter((item) => item.count > 0).map((item) => ({
    key: item.severity,
    label: item.severity || "UNKNOWN",
    count: item.count,
    color: severityColors[item.severity.toUpperCase()] ?? "#7d8da6",
  }));
  const services = data.service_counts.filter((item) => item.error_events > 0).slice(0, 8).map((item) => ({
    key: item.service,
    label: item.service || "Unknown service",
    count: item.error_events,
    color: "#537cae",
  }));
  const fingerprints = data.fingerprint_groups.filter((item) => item.count > 1).slice(0, 8).map((item, index) => ({
    key: item.fingerprint,
    label: `Pattern ${index + 1}`,
    count: item.count,
    color: "#488e87",
  }));

  return (
    <div className={styles.charts} aria-label="Incident charts">
      <TimelineChart data={data} bucket={bucket} zone={zone} />
      <div className={styles.comparisonGrid}>
        <HorizontalChart title="Severity" rows={severity} empty="No events" />
        <HorizontalChart title="Errors by service" rows={services} empty="No service errors" />
        <HorizontalChart title="Recurring patterns" rows={fingerprints} empty="No recurring patterns" />
      </div>
    </div>
  );
}
