"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAccount } from "@/components/m1/use-account";
import { apiGet, apiWrite, describeApiFailure } from "@/lib/api-client";
import { formatRelativeAge } from "@/lib/dashboard-api";

export type WorkspaceSummary = Readonly<{
  id: string;
  name: string;
  slug: string;
  description: string;
  my_role: "owner" | "responder" | "viewer";
  member_count: number;
  incident_count: number;
  webhook_count: number;
  created_at: string;
  updated_at: string;
}>;

type WorkspaceMember = Readonly<{
  id: string;
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: "owner" | "responder" | "viewer";
  created_at: string;
}>;

type AlertWebhook = Readonly<{
  id: string;
  name: string;
  provider: "generic" | "slack" | "discord" | "pagerduty";
  target_url: string;
  signing_secret_preview: string;
  signing_secret?: string;
  event_types: string[];
  min_severity: "low" | "medium" | "high" | "critical";
  is_active: boolean;
  delivery_count: number;
  last_delivery_status: string;
  created_at: string;
  updated_at: string;
}>;

type WebhookDelivery = Readonly<{
  id: string;
  event_type: string;
  incident_id: string | null;
  status: "delivered" | "failed" | "blocked" | "dry_run";
  http_status: number | null;
  latency_ms: number | null;
  request_payload: Record<string, unknown>;
  response_excerpt: string;
  error_message: string;
  created_at: string;
}>;

const ALL_WEBHOOK_EVENTS = [
  { key: "incident.created", label: "Incident created" },
  { key: "incident.status_changed", label: "Status changed" },
  { key: "postmortem.finalized", label: "Postmortem finalized" },
] as const;

const RBAC_MATRIX = [
  {
    role: "Owner",
    perms: "Manage workspace members, roles, alert webhooks, and incident deletion.",
  },
  {
    role: "Responder",
    perms: "Create and update incidents, upload logs, run AI investigations, and finalize postmortems.",
  },
  {
    role: "Viewer",
    perms: "Read-only access to dashboards, logs, analytics, topology, and postmortem exports.",
  },
] as const;

function deliveryBadge(status: string): string {
  if (status === "delivered") return "if-badge if-badge-resolved";
  if (status === "dry_run") return "if-badge if-badge-investigating";
  if (status === "blocked") return "if-badge if-badge-medium";
  return "if-badge if-badge-critical";
}

export function WorkspacesPanel() {
  const account = useAccount();
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"members" | "webhooks">("members");
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [webhooks, setWebhooks] = useState<AlertWebhook[]>([]);
  const [deliveriesByHook, setDeliveriesByHook] = useState<Record<string, WebhookDelivery[]>>({});
  const [expandedHookId, setExpandedHookId] = useState<string | null>(null);
  const [revealedSecret, setRevealedSecret] = useState<{ name: string; secret: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Collapsible forms
  const [showNewWs, setShowNewWs] = useState(false);
  const [wsName, setWsName] = useState("");
  const [wsDesc, setWsDesc] = useState("");
  const [creatingWs, setCreatingWs] = useState(false);

  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"owner" | "responder" | "viewer">("responder");
  const [inviting, setInviting] = useState(false);

  const [showHookForm, setShowHookForm] = useState(false);
  const [whName, setWhName] = useState("");
  const [whProvider, setWhProvider] = useState<AlertWebhook["provider"]>("slack");
  const [whUrl, setWhUrl] = useState("");
  const [whSeverity, setWhSeverity] = useState<AlertWebhook["min_severity"]>("high");
  const [whEvents, setWhEvents] = useState<string[]>([
    "incident.created",
    "incident.status_changed",
    "postmortem.finalized",
  ]);
  const [creatingHook, setCreatingHook] = useState(false);
  const [testingHookId, setTestingHookId] = useState<string | null>(null);

  const loadWorkspaces = useCallback(async (preferredId?: string) => {
    const list = await apiGet<WorkspaceSummary[]>("workspaces");
    setWorkspaces(list);
    setActiveId((current) => {
      if (preferredId && list.some((w) => w.id === preferredId)) return preferredId;
      if (current && list.some((w) => w.id === current)) return current;
      return list[0]?.id ?? "";
    });
  }, []);

  const loadWorkspaceDetails = useCallback(async (workspaceId: string) => {
    if (!workspaceId) {
      setMembers([]);
      setWebhooks([]);
      return;
    }
    const encoded = encodeURIComponent(workspaceId);
    const [m, w] = await Promise.all([
      apiGet<WorkspaceMember[]>(`workspaces/${encoded}/members`),
      apiGet<AlertWebhook[]>(`workspaces/${encoded}/webhooks`),
    ]);
    setMembers(m);
    setWebhooks(w);
  }, []);

  useEffect(() => {
    if (account.state !== "signed-in") return;
    let active = true;
    apiGet<WorkspaceSummary[]>("workspaces")
      .then((list) => {
        if (!active) return;
        setWorkspaces(list);
        setActiveId((current) =>
          current && list.some((w) => w.id === current) ? current : (list[0]?.id ?? ""),
        );
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
  }, [account.state]);

  useEffect(() => {
    if (account.state !== "signed-in" || !activeId) return;
    let active = true;
    const encoded = encodeURIComponent(activeId);
    Promise.all([
      apiGet<WorkspaceMember[]>(`workspaces/${encoded}/members`),
      apiGet<AlertWebhook[]>(`workspaces/${encoded}/webhooks`),
    ])
      .then(([m, w]) => {
        if (!active) return;
        setMembers(m);
        setWebhooks(w);
      })
      .catch((failure: unknown) => {
        if (active) setError(describeApiFailure(failure));
      });
    return () => {
      active = false;
    };
  }, [account.state, activeId]);

  const activeWorkspace = workspaces.find((w) => w.id === activeId) ?? null;
  const isOwner = activeWorkspace?.my_role === "owner";

  async function createWorkspace(event: FormEvent) {
    event.preventDefault();
    if (wsName.trim().length < 2 || creatingWs) return;
    setCreatingWs(true);
    setError("");
    setNotice("");
    try {
      const created = await apiWrite<WorkspaceSummary>("workspaces", "POST", {
        name: wsName.trim(),
        description: wsDesc.trim(),
      });
      setWsName("");
      setWsDesc("");
      setShowNewWs(false);
      await loadWorkspaces(created.id);
      setNotice(`Workspace "${created.name}" created.`);
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    } finally {
      setCreatingWs(false);
    }
  }

  async function inviteMember(event: FormEvent) {
    event.preventDefault();
    if (!activeId || !inviteEmail.trim() || inviting) return;
    setInviting(true);
    setError("");
    setNotice("");
    try {
      await apiWrite<WorkspaceMember>(
        `workspaces/${encodeURIComponent(activeId)}/members`,
        "POST",
        { email: inviteEmail.trim(), role: inviteRole },
      );
      setInviteEmail("");
      setShowInviteForm(false);
      await Promise.all([loadWorkspaceDetails(activeId), loadWorkspaces(activeId)]);
      setNotice("Team member added.");
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    } finally {
      setInviting(false);
    }
  }

  async function changeRole(membershipId: string, nextRole: "owner" | "responder" | "viewer") {
    if (!activeId) return;
    setError("");
    try {
      await apiWrite<WorkspaceMember>(
        `workspaces/${encodeURIComponent(activeId)}/members/${encodeURIComponent(membershipId)}`,
        "PATCH",
        { role: nextRole },
      );
      await Promise.all([loadWorkspaceDetails(activeId), loadWorkspaces(activeId)]);
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    }
  }

  async function removeMember(membershipId: string) {
    if (!activeId) return;
    setError("");
    try {
      await apiWrite<void>(
        `workspaces/${encodeURIComponent(activeId)}/members/${encodeURIComponent(membershipId)}`,
        "DELETE",
      );
      await Promise.all([loadWorkspaceDetails(activeId), loadWorkspaces(activeId)]);
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    }
  }

  async function createWebhook(event: FormEvent) {
    event.preventDefault();
    if (!activeId || whName.trim().length < 2 || !whUrl.trim() || creatingHook) return;
    setCreatingHook(true);
    setError("");
    setNotice("");
    setRevealedSecret(null);
    try {
      const created = await apiWrite<AlertWebhook>(
        `workspaces/${encodeURIComponent(activeId)}/webhooks`,
        "POST",
        {
          name: whName.trim(),
          provider: whProvider,
          target_url: whUrl.trim(),
          event_types: whEvents.length ? whEvents : ["incident.created"],
          min_severity: whSeverity,
          is_active: true,
        },
      );
      setWhName("");
      setWhUrl("");
      setShowHookForm(false);
      if (created.signing_secret) {
        setRevealedSecret({ name: created.name, secret: created.signing_secret });
      }
      await Promise.all([loadWorkspaceDetails(activeId), loadWorkspaces(activeId)]);
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    } finally {
      setCreatingHook(false);
    }
  }

  async function toggleWebhookActive(hook: AlertWebhook) {
    if (!activeId) return;
    setError("");
    try {
      await apiWrite<AlertWebhook>(
        `workspaces/${encodeURIComponent(activeId)}/webhooks/${encodeURIComponent(hook.id)}`,
        "PATCH",
        { is_active: !hook.is_active },
      );
      await loadWorkspaceDetails(activeId);
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    }
  }

  async function deleteWebhook(hookId: string) {
    if (!activeId) return;
    setError("");
    try {
      await apiWrite<void>(
        `workspaces/${encodeURIComponent(activeId)}/webhooks/${encodeURIComponent(hookId)}`,
        "DELETE",
      );
      await Promise.all([loadWorkspaceDetails(activeId), loadWorkspaces(activeId)]);
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    }
  }

  async function loadDeliveries(hookId: string) {
    if (!activeId) return;
    const rows = await apiGet<WebhookDelivery[]>(
      `workspaces/${encodeURIComponent(activeId)}/webhooks/${encodeURIComponent(hookId)}/deliveries`,
    );
    setDeliveriesByHook((cur) => ({ ...cur, [hookId]: rows }));
  }

  async function testWebhook(hookId: string, dryRun: boolean) {
    if (!activeId || testingHookId) return;
    setTestingHookId(`${hookId}:${dryRun}`);
    setError("");
    setNotice("");
    try {
      const delivery = await apiWrite<WebhookDelivery>(
        `workspaces/${encodeURIComponent(activeId)}/webhooks/${encodeURIComponent(hookId)}/test`,
        "POST",
        { dry_run: dryRun },
      );
      setExpandedHookId(hookId);
      await Promise.all([loadDeliveries(hookId), loadWorkspaceDetails(activeId)]);
      setNotice(
        dryRun
          ? `Dry-run payload signed and recorded (${delivery.event_type}).`
          : `Live test finished with "${delivery.status}"${delivery.http_status ? ` (HTTP ${delivery.http_status})` : ""}.`,
      );
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    } finally {
      setTestingHookId(null);
    }
  }

  if (account.state === "loading") return <p role="status">Checking your session…</p>;
  if (account.state === "error") return <p role="alert" className="m1-error">{account.message}</p>;
  if (account.state === "signed-out") {
    return (
      <section className="panel m1-prompt">
        <h2>Team workspaces &amp; alert routing</h2>
        <p>Sign in to manage workspaces, RBAC roles, and signed outbound webhooks.</p>
        <Link className="button button-primary" href="/login">Sign in</Link>
      </section>
    );
  }

  return (
    <div className="ws-stack">
      {error && <p role="alert" className="m1-error" style={{ margin: 0 }}>{error}</p>}
      {notice && <p role="status" className="m2-status-banner" style={{ margin: 0 }}>{notice}</p>}

      {loading ? (
        <p role="status" className="m1-hint">Loading workspaces…</p>
      ) : (
        <div className="ws-layout">
          <aside className="panel ws-sidebar-panel" aria-label="Your workspaces">
            <div className="panel-header">
              <h2>Teams ({workspaces.length})</h2>
              <button
                type="button"
                className={showNewWs ? "quiet-btn is-active" : "quiet-btn is-accent"}
                onClick={() => setShowNewWs((cur) => !cur)}
              >
                {showNewWs ? "Cancel" : "+ New"}
              </button>
            </div>

            {showNewWs && (
              <form className="ws-inline-form" onSubmit={(e) => void createWorkspace(e)}>
                <label className="sr-only" htmlFor="new-ws-name">Workspace name</label>
                <input
                  id="new-ws-name"
                  type="text"
                  required
                  minLength={2}
                  maxLength={120}
                  value={wsName}
                  onChange={(e) => setWsName(e.target.value)}
                  placeholder="Workspace name (e.g. Payments SRE)"
                />
                <label className="sr-only" htmlFor="new-ws-desc">Workspace description</label>
                <input
                  id="new-ws-desc"
                  type="text"
                  maxLength={300}
                  value={wsDesc}
                  onChange={(e) => setWsDesc(e.target.value)}
                  placeholder="Short description (optional)"
                />
                <button type="submit" className="demo-launch-btn" disabled={creatingWs}>
                  {creatingWs ? "Creating…" : "Create"}
                </button>
              </form>
            )}

            {workspaces.length === 0 ? (
              <div className="m1-empty">No workspaces yet.</div>
            ) : (
              <ul className="ws-list">
                {workspaces.map((ws) => (
                  <li key={ws.id}>
                    <button
                      type="button"
                      className={ws.id === activeId ? "ws-list-item is-active" : "ws-list-item"}
                      onClick={() => {
                        setActiveId(ws.id);
                        setRevealedSecret(null);
                        setShowInviteForm(false);
                        setShowHookForm(false);
                        setNotice("");
                      }}
                    >
                      <div className="ws-list-top">
                        <strong>{ws.name}</strong>
                        <span className="ws-role-label">{ws.my_role}</span>
                      </div>
                      <span className="mono ws-list-meta">
                        {ws.member_count} members · {ws.webhook_count} webhooks
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </aside>

          <div className="ws-main">
            {!activeWorkspace ? (
              <section className="panel m1-prompt">
                <h2>Create your first workspace</h2>
                <p>
                  Group incidents by team, assign Owner / Responder / Viewer roles, and configure signed
                  Slack, Discord, or PagerDuty webhooks.
                </p>
                <button
                  type="button"
                  className="button button-primary"
                  onClick={() => setShowNewWs(true)}
                >
                  Create workspace
                </button>
              </section>
            ) : (
              <section className="panel">
                <div className="panel-header panel-header-with-actions">
                  <div>
                    <h2>{activeWorkspace.name}</h2>
                    <p>
                      {(activeWorkspace.description || "Shared incident workspace").replace(/\.$/, "")} ·{" "}
                      <span className="mono">/{activeWorkspace.slug}</span>
                    </p>
                  </div>
                  <div className="stage-toolbar-controls">
                    <div className="dash-filter-tabs" role="tablist" aria-label="Workspace settings">
                      <button
                        type="button"
                        role="tab"
                        aria-selected={activeTab === "members"}
                        className={activeTab === "members" ? "dash-filter-tab is-active" : "dash-filter-tab"}
                        onClick={() => setActiveTab("members")}
                      >
                        Members ({members.length})
                      </button>
                      <button
                        type="button"
                        role="tab"
                        aria-selected={activeTab === "webhooks"}
                        className={activeTab === "webhooks" ? "dash-filter-tab is-active" : "dash-filter-tab"}
                        onClick={() => setActiveTab("webhooks")}
                      >
                        Webhooks ({webhooks.length})
                      </button>
                    </div>
                    {isOwner && activeTab === "members" && (
                      <button
                        type="button"
                        className={showInviteForm ? "quiet-btn is-active" : "quiet-btn is-accent"}
                        aria-expanded={showInviteForm}
                        onClick={() => setShowInviteForm((cur) => !cur)}
                      >
                        {showInviteForm ? "Cancel" : "+ Add member"}
                      </button>
                    )}
                    {isOwner && activeTab === "webhooks" && (
                      <button
                        type="button"
                        className={showHookForm ? "quiet-btn is-active" : "quiet-btn is-accent"}
                        aria-expanded={showHookForm}
                        onClick={() => setShowHookForm((cur) => !cur)}
                      >
                        {showHookForm ? "Cancel" : "+ Add webhook"}
                      </button>
                    )}
                  </div>
                </div>

                {activeTab === "members" ? (
                  <div className="ws-tab-body">
                    {isOwner && showInviteForm && (
                      <form className="ws-member-form" onSubmit={(e) => void inviteMember(e)}>
                        <div className="m2-filter-field">
                          <label htmlFor="invite-email">Member email</label>
                          <input
                            id="invite-email"
                            type="email"
                            required
                            value={inviteEmail}
                            onChange={(e) => setInviteEmail(e.target.value)}
                            placeholder="engineer@company.com"
                          />
                        </div>
                        <div className="m2-filter-field">
                          <label htmlFor="invite-role">Role</label>
                          <select
                            id="invite-role"
                            value={inviteRole}
                            onChange={(e) => setInviteRole(e.target.value as "owner" | "responder" | "viewer")}
                          >
                            <option value="responder">Responder</option>
                            <option value="viewer">Viewer</option>
                            <option value="owner">Owner</option>
                          </select>
                        </div>
                        <button type="submit" className="demo-launch-btn" disabled={inviting}>
                          {inviting ? "Adding…" : "Add member"}
                        </button>
                      </form>
                    )}

                    <div className="table-scroll">
                      <table className="incident-table m1-table">
                        <thead>
                          <tr>
                            <th scope="col">Member</th>
                            <th scope="col">Role</th>
                            <th scope="col">Added</th>
                            {isOwner && <th scope="col"><span className="sr-only">Actions</span></th>}
                          </tr>
                        </thead>
                        <tbody>
                          {members.map((member) => (
                            <tr key={member.id}>
                              <td>
                                <strong>{member.email}</strong>
                                {(member.first_name || member.last_name) && (
                                  <div className="dash-inc-meta">
                                    {[member.first_name, member.last_name].filter(Boolean).join(" ")}
                                  </div>
                                )}
                              </td>
                              <td>
                                {isOwner ? (
                                  <select
                                    aria-label={`Role for ${member.email}`}
                                    className="ws-role-select"
                                    value={member.role}
                                    onChange={(e) =>
                                      void changeRole(
                                        member.id,
                                        e.target.value as "owner" | "responder" | "viewer",
                                      )
                                    }
                                  >
                                    <option value="owner">Owner</option>
                                    <option value="responder">Responder</option>
                                    <option value="viewer">Viewer</option>
                                  </select>
                                ) : (
                                  <span className="ws-role-label">{member.role}</span>
                                )}
                              </td>
                              <td className="m1-time">{formatRelativeAge(member.created_at)}</td>
                              {isOwner && (
                                <td style={{ textAlign: "right" }}>
                                  <button
                                    type="button"
                                    className="ghost-danger-btn"
                                    onClick={() => void removeMember(member.id)}
                                  >
                                    Remove
                                  </button>
                                </td>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <details className="ws-rbac-details">
                      <summary>Role permissions reference</summary>
                      <dl className="ws-rbac-list">
                        {RBAC_MATRIX.map((row) => (
                          <div key={row.role}>
                            <dt>{row.role}</dt>
                            <dd>{row.perms}</dd>
                          </div>
                        ))}
                      </dl>
                    </details>
                  </div>
                ) : (
                  <div className="ws-tab-body">
                    {revealedSecret && (
                      <div className="ws-secret-banner" role="status">
                        <div>
                          <strong>One-time HMAC signing secret for {revealedSecret.name}:</strong>
                          <p className="m1-hint" style={{ margin: "4px 0 0" }}>
                            Save now to verify <code>X-IncidentForge-Signature</code>. It will be masked afterward.
                          </p>
                        </div>
                        <code className="ws-secret-code">{revealedSecret.secret}</code>
                      </div>
                    )}

                    {isOwner && showHookForm && (
                      <form className="ws-hook-form" onSubmit={(e) => void createWebhook(e)}>
                        <div className="ws-hook-grid">
                          <div className="m2-filter-field">
                            <label htmlFor="wh-name">Name</label>
                            <input
                              id="wh-name"
                              type="text"
                              required
                              minLength={2}
                              maxLength={120}
                              value={whName}
                              onChange={(e) => setWhName(e.target.value)}
                              placeholder="e.g. #sre-alerts Slack"
                            />
                          </div>
                          <div className="m2-filter-field">
                            <label htmlFor="wh-provider">Provider</label>
                            <select
                              id="wh-provider"
                              value={whProvider}
                              onChange={(e) => setWhProvider(e.target.value as AlertWebhook["provider"])}
                            >
                              <option value="slack">Slack (Block Kit)</option>
                              <option value="discord">Discord (Embeds)</option>
                              <option value="pagerduty">PagerDuty (Events v2)</option>
                              <option value="generic">Generic Signed JSON</option>
                            </select>
                          </div>
                          <div className="m2-filter-field">
                            <label htmlFor="wh-severity">Min severity</label>
                            <select
                              id="wh-severity"
                              value={whSeverity}
                              onChange={(e) => setWhSeverity(e.target.value as AlertWebhook["min_severity"])}
                            >
                              <option value="low">Low &amp; above</option>
                              <option value="medium">Medium &amp; above</option>
                              <option value="high">High &amp; Critical</option>
                              <option value="critical">Critical only</option>
                            </select>
                          </div>
                        </div>

                        <div className="m2-filter-field">
                          <label htmlFor="wh-url">HTTPS target URL (SSRF-guarded)</label>
                          <input
                            id="wh-url"
                            type="url"
                            required
                            maxLength={500}
                            value={whUrl}
                            onChange={(e) => setWhUrl(e.target.value)}
                            placeholder="https://hooks.slack.com/services/..."
                          />
                        </div>

                        <div className="ws-hook-footer">
                          <div className="ws-event-checks" role="group" aria-label="Subscribed events">
                            {ALL_WEBHOOK_EVENTS.map((ev) => {
                              const checked = whEvents.includes(ev.key);
                              return (
                                <label key={ev.key} className="ws-check-label">
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    onChange={(e) =>
                                      setWhEvents((cur) =>
                                        e.target.checked
                                          ? [...cur, ev.key]
                                          : cur.filter((x) => x !== ev.key),
                                      )
                                    }
                                  />
                                  <span>{ev.label}</span>
                                </label>
                              );
                            })}
                          </div>
                          <button type="submit" className="demo-launch-btn" disabled={creatingHook}>
                            {creatingHook ? "Saving…" : "Save webhook"}
                          </button>
                        </div>
                      </form>
                    )}

                    {webhooks.length === 0 ? (
                      <div className="m1-empty">
                        No alert webhooks configured yet.{isOwner ? " Click + Add webhook to connect Slack, Discord, or PagerDuty." : ""}
                      </div>
                    ) : (
                      <ul className="ws-hook-list">
                        {webhooks.map((hook) => {
                          const expanded = expandedHookId === hook.id;
                          const deliveries = deliveriesByHook[hook.id] ?? [];
                          return (
                            <li className="ws-hook-row" key={hook.id}>
                              <div className="ws-hook-card-top">
                                <div className="ws-hook-info">
                                  <div className="ws-hook-title-row">
                                    <strong>{hook.name}</strong>
                                    <span className={`if-badge ${hook.is_active ? "if-badge-resolved" : "if-badge-neutral"}`}>
                                      {hook.is_active ? "Active" : "Paused"}
                                    </span>
                                    <span className="inc-ctx-age">
                                      {hook.provider} · ≥ {hook.min_severity}
                                    </span>
                                  </div>
                                  <p className="ws-hook-meta mono">
                                    {hook.target_url} · HMAC {hook.signing_secret_preview}
                                  </p>
                                  <p className="ws-hook-events">
                                    Events: {hook.event_types.join(", ")}
                                  </p>
                                </div>

                                <div className="ws-hook-actions">
                                  {isOwner && (
                                    <button
                                      type="button"
                                      className="quiet-btn"
                                      disabled={testingHookId !== null}
                                      onClick={() => void testWebhook(hook.id, true)}
                                    >
                                      {testingHookId === `${hook.id}:true` ? "Signing…" : "Dry-run"}
                                    </button>
                                  )}
                                  <button
                                    type="button"
                                    className={expanded ? "quiet-btn is-active" : "quiet-btn"}
                                    onClick={() => {
                                      if (expanded) {
                                        setExpandedHookId(null);
                                      } else {
                                        setExpandedHookId(hook.id);
                                        void loadDeliveries(hook.id);
                                      }
                                    }}
                                  >
                                    {expanded ? "Hide logs" : `Logs (${hook.delivery_count})`}
                                  </button>
                                  {isOwner && (
                                    <details className="ws-more-menu">
                                      <summary aria-label={`More actions for ${hook.name}`}>⋯</summary>
                                      <div className="ws-more-popover">
                                        <button
                                          type="button"
                                          disabled={testingHookId !== null}
                                          onClick={() => void testWebhook(hook.id, false)}
                                        >
                                          {testingHookId === `${hook.id}:false` ? "Sending…" : "Send live ping"}
                                        </button>
                                        <button
                                          type="button"
                                          onClick={() => void toggleWebhookActive(hook)}
                                        >
                                          {hook.is_active ? "Pause webhook" : "Resume webhook"}
                                        </button>
                                        <button
                                          type="button"
                                          className="is-danger"
                                          onClick={() => void deleteWebhook(hook.id)}
                                        >
                                          Delete webhook
                                        </button>
                                      </div>
                                    </details>
                                  )}
                                </div>
                              </div>

                              {expanded && (
                                <div className="ws-deliveries">
                                  {deliveries.length === 0 ? (
                                    <p className="m1-hint" style={{ margin: 0 }}>
                                      No deliveries yet. Run a dry-run or live ping to inspect signed payloads.
                                    </p>
                                  ) : (
                                    <ul className="ws-delivery-list">
                                      {deliveries.map((del) => (
                                        <li className="ws-delivery-row" key={del.id}>
                                          <div className="ws-delivery-head">
                                            <span className={deliveryBadge(del.status)}>
                                              {del.status.replaceAll("_", " ")}
                                            </span>
                                            <code className="mono">{del.event_type}</code>
                                            {del.http_status && <span className="mono">HTTP {del.http_status}</span>}
                                            {del.latency_ms !== null && <span className="mono">{del.latency_ms}ms</span>}
                                            <span className="inc-ctx-age">
                                              {formatRelativeAge(del.created_at)}
                                            </span>
                                          </div>
                                          {(del.error_message || del.response_excerpt) && (
                                            <p className="ws-delivery-note">
                                              {del.error_message || del.response_excerpt}
                                            </p>
                                          )}
                                          <details className="ws-delivery-payload">
                                            <summary>Inspect payload</summary>
                                            <pre>{JSON.stringify(del.request_payload, null, 2)}</pre>
                                          </details>
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                )}
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
