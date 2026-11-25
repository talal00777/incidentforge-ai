"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useAccount } from "@/components/m1/use-account";
import { apiGet, apiWrite, describeApiFailure, type Incident } from "@/lib/api-client";
import { formatRelativeAge } from "@/lib/dashboard-api";

type TimelineItem = Readonly<{
  id: string;
  source_kind: "operator" | "audit" | "source" | "snapshot" | "ai" | "postmortem";
  entry_type: string;
  body: string;
  actor_label: string;
  occurred_at: string;
  deletable: boolean;
}>;

type ActionItem = Readonly<{
  id: string;
  title: string;
  owner_label: string;
  priority: "p0" | "p1" | "p2" | "p3";
  status: "open" | "in_progress" | "done";
  due_at: string | null;
  completed_at: string | null;
  created_by_email: string;
  created_at: string;
  updated_at: string;
}>;

type TimelineFilter = "all" | "operator" | "system";
type EntryType = "note" | "mitigation" | "milestone" | "decision" | "handoff";

const ENTRY_TYPE_LABELS: Record<EntryType, string> = {
  note: "Operator note",
  mitigation: "Mitigation",
  milestone: "Milestone",
  decision: "Decision",
  handoff: "Shift handoff",
};

const NEXT_STATUS: Record<ActionItem["status"], ActionItem["status"]> = {
  open: "in_progress",
  in_progress: "done",
  done: "open",
};

function statusLabel(value: ActionItem["status"]): string {
  if (value === "in_progress") return "In progress";
  if (value === "done") return "Done";
  return "Open";
}

function formatUtcStamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return (
    new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      timeZone: "UTC",
    }).format(date) + " UTC"
  );
}

export function WarRoomPanel({ incidentId }: { incidentId: string }) {
  const account = useAccount();
  const encodedId = encodeURIComponent(incidentId);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [userRole, setUserRole] = useState<string>("owner");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tlFilter, setTlFilter] = useState<TimelineFilter>("all");

  // Collapsible composer controls
  const [showComposer, setShowComposer] = useState(false);
  const [entryType, setEntryType] = useState<EntryType>("note");
  const [noteBody, setNoteBody] = useState("");
  const [postingNote, setPostingNote] = useState(false);

  const [showActionForm, setShowActionForm] = useState(false);
  const [actionTitle, setActionTitle] = useState("");
  const [actionPriority, setActionPriority] = useState<ActionItem["priority"]>("p1");
  const [actionOwner, setActionOwner] = useState("");
  const [addingAction, setAddingAction] = useState(false);

  const canWrite = userRole !== "viewer";

  useEffect(() => {
    if (account.state !== "signed-in") return;
    let active = true;
    Promise.all([
      apiGet<TimelineItem[]>(`incidents/${encodedId}/timeline`),
      apiGet<ActionItem[]>(`incidents/${encodedId}/action-items`),
      apiGet<Incident & { user_role?: string }>(`incidents/${encodedId}`).catch(() => null),
    ])
      .then(([tl, items, inc]) => {
        if (!active) return;
        setTimeline(tl);
        setActions(items);
        if (inc?.user_role) setUserRole(inc.user_role);
        setError("");
      })
      .catch((failure: unknown) => {
        if (active) setError(describeApiFailure(failure));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [account.state, encodedId]);

  const visibleTimeline = useMemo(() => {
    if (tlFilter === "operator") return timeline.filter((item) => item.source_kind === "operator");
    if (tlFilter === "system") return timeline.filter((item) => item.source_kind !== "operator");
    return timeline;
  }, [timeline, tlFilter]);

  const doneCount = useMemo(() => actions.filter((a) => a.status === "done").length, [actions]);
  const progressPct = actions.length > 0 ? Math.round((doneCount / actions.length) * 100) : 0;

  async function submitNote(event: FormEvent) {
    event.preventDefault();
    const cleaned = noteBody.trim();
    if (cleaned.length < 2 || postingNote || !canWrite) return;
    setPostingNote(true);
    setError("");
    try {
      const created = await apiWrite<TimelineItem>(`incidents/${encodedId}/timeline`, "POST", {
        entry_type: entryType,
        body: cleaned,
      });
      setTimeline((cur) => [created, ...cur]);
      setNoteBody("");
      setShowComposer(false);
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    } finally {
      setPostingNote(false);
    }
  }

  async function deleteNote(entryId: string) {
    if (!canWrite) return;
    try {
      await apiWrite<void>(`incidents/${encodedId}/timeline/${encodeURIComponent(entryId)}`, "DELETE");
      setTimeline((cur) => cur.filter((item) => item.id !== entryId));
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    }
  }

  async function submitActionItem(event: FormEvent) {
    event.preventDefault();
    const cleaned = actionTitle.trim();
    if (cleaned.length < 2 || addingAction || !canWrite) return;
    setAddingAction(true);
    setError("");
    try {
      const created = await apiWrite<ActionItem>(`incidents/${encodedId}/action-items`, "POST", {
        title: cleaned,
        priority: actionPriority,
        owner_label: actionOwner.trim(),
      });
      setActions((cur) => [created, ...cur]);
      setActionTitle("");
      setActionOwner("");
      setShowActionForm(false);
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    } finally {
      setAddingAction(false);
    }
  }

  async function cycleActionStatus(item: ActionItem) {
    if (!canWrite) return;
    const next = NEXT_STATUS[item.status];
    try {
      const updated = await apiWrite<ActionItem>(
        `incidents/${encodedId}/action-items/${encodeURIComponent(item.id)}`,
        "PATCH",
        { status: next },
      );
      setActions((cur) => cur.map((row) => (row.id === updated.id ? updated : row)));
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    }
  }

  async function deleteActionItem(itemId: string) {
    if (!canWrite) return;
    try {
      await apiWrite<void>(
        `incidents/${encodedId}/action-items/${encodeURIComponent(itemId)}`,
        "DELETE",
      );
      setActions((cur) => cur.filter((row) => row.id !== itemId));
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    }
  }

  if (account.state === "loading") return <p role="status">Checking your session…</p>;
  if (account.state === "error") return <p role="alert" className="m1-error">{account.message}</p>;
  if (account.state === "signed-out") {
    return (
      <section className="panel m1-prompt">
        <p>Please <Link href="/login">sign in</Link> to open the incident war room.</p>
      </section>
    );
  }

  return (
    <div className="warroom-stack">
      <header className="stage-toolbar">
        <h1 className="stage-title">War room</h1>
        {!canWrite && <span className="if-badge if-badge-neutral">Read-only viewer</span>}
      </header>

      {error && <p role="alert" className="m1-error" style={{ margin: 0 }}>{error}</p>}

      {loading ? (
        <p role="status" className="m1-hint">Loading war room…</p>
      ) : (
        <div className="warroom-grid">
          <section className="panel" aria-labelledby="warroom-timeline-heading">
            <div className="panel-header panel-header-with-actions">
              <h2 id="warroom-timeline-heading">Timeline</h2>
              <div className="stage-toolbar-controls">
                <div className="dash-filter-tabs" role="tablist" aria-label="Filter timeline entries">
                  {(
                    [
                      ["all", "All"],
                      ["operator", "Operator"],
                      ["system", "System"],
                    ] as const
                  ).map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      role="tab"
                      aria-selected={tlFilter === key}
                      className={tlFilter === key ? "dash-filter-tab is-active" : "dash-filter-tab"}
                      onClick={() => setTlFilter(key)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {canWrite && (
                  <button
                    type="button"
                    className={showComposer ? "quiet-btn is-active" : "quiet-btn is-accent"}
                    aria-expanded={showComposer}
                    onClick={() => setShowComposer((cur) => !cur)}
                  >
                    {showComposer ? "Cancel" : "+ Post update"}
                  </button>
                )}
              </div>
            </div>

            {canWrite && showComposer && (
              <form className="warroom-composer" onSubmit={(e) => void submitNote(e)}>
                <div className="warroom-composer-row">
                  <label className="sr-only" htmlFor="timeline-entry-type">Entry category</label>
                  <select
                    id="timeline-entry-type"
                    value={entryType}
                    onChange={(e) => setEntryType(e.target.value as EntryType)}
                  >
                    {(Object.entries(ENTRY_TYPE_LABELS) as [EntryType, string][]).map(([k, label]) => (
                      <option key={k} value={k}>{label}</option>
                    ))}
                  </select>
                  <button
                    type="submit"
                    className="demo-launch-btn"
                    disabled={postingNote || noteBody.trim().length < 2}
                  >
                    {postingNote ? "Posting…" : "Post update"}
                  </button>
                </div>
                <label className="sr-only" htmlFor="timeline-note-body">Timeline update</label>
                <textarea
                  id="timeline-note-body"
                  rows={2}
                  maxLength={2000}
                  value={noteBody}
                  onChange={(e) => setNoteBody(e.target.value)}
                  placeholder="Record a mitigation step, triage hypothesis, or handoff note…"
                />
              </form>
            )}

            {visibleTimeline.length === 0 ? (
              <div className="m1-empty">No timeline events yet.</div>
            ) : (
              <ol className="warroom-feed">
                {visibleTimeline.map((item) => (
                  <li className={`warroom-entry kind-${item.source_kind}`} key={item.id}>
                    <span className="warroom-entry-dot" aria-hidden="true" />
                    <div className="warroom-entry-content">
                      <div className="warroom-entry-meta">
                        <span className="warroom-entry-kind">
                          {item.entry_type.replaceAll("_", " ")}
                        </span>
                        <span aria-hidden="true">·</span>
                        <span className="mono">{item.actor_label || "system"}</span>
                        <span aria-hidden="true">·</span>
                        <time dateTime={item.occurred_at} title={formatUtcStamp(item.occurred_at)}>
                          {formatRelativeAge(item.occurred_at)}
                        </time>
                        {item.deletable && canWrite && (
                          <button
                            type="button"
                            className="ghost-danger-btn"
                            onClick={() => void deleteNote(item.id)}
                            aria-label="Delete timeline note"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                      <p className="warroom-entry-body">{item.body}</p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="panel" aria-labelledby="warroom-actions-heading">
            <div className="panel-header panel-header-with-actions">
              <div className="stage-toolbar-left">
                <h2 id="warroom-actions-heading">Action items</h2>
                <span className="inc-ctx-age">
                  {doneCount}/{actions.length}
                </span>
              </div>
              {canWrite && (
                <button
                  type="button"
                  className={showActionForm ? "quiet-btn is-active" : "quiet-btn is-accent"}
                  aria-expanded={showActionForm}
                  onClick={() => setShowActionForm((cur) => !cur)}
                >
                  {showActionForm ? "Cancel" : "+ Add"}
                </button>
              )}
            </div>

            {actions.length > 0 && (
              <div className="warroom-progress-slim" aria-hidden="true">
                <span style={{ width: `${progressPct}%` }} />
              </div>
            )}

            {canWrite && showActionForm && (
              <form className="warroom-action-form" onSubmit={(e) => void submitActionItem(e)}>
                <label className="sr-only" htmlFor="action-item-title">Action title</label>
                <input
                  id="action-item-title"
                  type="text"
                  maxLength={200}
                  value={actionTitle}
                  onChange={(e) => setActionTitle(e.target.value)}
                  placeholder="Remediation task (e.g. Cap PgBouncer pool timeout)"
                />
                <div className="warroom-action-form-row">
                  <label className="sr-only" htmlFor="action-item-priority">Priority</label>
                  <select
                    id="action-item-priority"
                    value={actionPriority}
                    onChange={(e) => setActionPriority(e.target.value as ActionItem["priority"])}
                  >
                    <option value="p0">P0 · Immediate</option>
                    <option value="p1">P1 · High</option>
                    <option value="p2">P2 · Medium</option>
                    <option value="p3">P3 · Follow-up</option>
                  </select>
                  <label className="sr-only" htmlFor="action-item-owner">Owner</label>
                  <input
                    id="action-item-owner"
                    type="text"
                    maxLength={120}
                    value={actionOwner}
                    onChange={(e) => setActionOwner(e.target.value)}
                    placeholder="Owner (optional)"
                  />
                  <button
                    type="submit"
                    className="demo-launch-btn"
                    disabled={addingAction || actionTitle.trim().length < 2}
                  >
                    {addingAction ? "Adding…" : "Add"}
                  </button>
                </div>
              </form>
            )}

            {actions.length === 0 ? (
              <div className="m1-empty">No action items tracked yet.</div>
            ) : (
              <ul className="warroom-action-list">
                {actions.map((item) => (
                  <li
                    key={item.id}
                    className={item.status === "done" ? "warroom-action-item is-done" : "warroom-action-item"}
                  >
                    <button
                      type="button"
                      className={`warroom-status-toggle is-${item.status}`}
                      disabled={!canWrite}
                      onClick={() => void cycleActionStatus(item)}
                      title={canWrite ? `Status: ${statusLabel(item.status)} (click to advance)` : statusLabel(item.status)}
                      aria-label={`Toggle status for ${item.title}: currently ${statusLabel(item.status)}`}
                    >
                      {item.status === "done" ? "✓" : item.status === "in_progress" ? "◐" : "○"}
                    </button>
                    <div className="warroom-action-body">
                      <span className="warroom-action-title">{item.title}</span>
                      <div className="warroom-action-meta">
                        <span className={`warroom-prio-text prio-${item.priority}`}>
                          {item.priority.toUpperCase()}
                        </span>
                        <span aria-hidden="true">·</span>
                        <span>{statusLabel(item.status)}</span>
                        {item.owner_label && (
                          <>
                            <span aria-hidden="true">·</span>
                            <span className="mono">{item.owner_label}</span>
                          </>
                        )}
                      </div>
                    </div>
                    {canWrite && (
                      <button
                        type="button"
                        className="ghost-danger-btn"
                        onClick={() => void deleteActionItem(item.id)}
                        aria-label={`Delete action item ${item.title}`}
                      >
                        ✕
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
