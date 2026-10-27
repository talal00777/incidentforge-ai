"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Incident, apiGet, apiWrite, describeApiFailure } from "@/lib/api-client";
import { useAccount } from "@/components/m1/use-account";

export function IncidentDetail() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const account = useAccount();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [impact, setImpact] = useState("");
  const [status, setStatus] = useState<Incident["status"]>("open");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const applyIncident = useCallback((record: Incident) => {
    setIncident(record);
    setTitle(record.title);
    setDescription(record.description);
    setImpact(record.impact_notes);
    setStatus(record.status);
  }, []);

  const load = useCallback(
    () => apiGet<Incident>(`incidents/${encodeURIComponent(params.id)}`),
    [params.id],
  );

  useEffect(() => {
    if (account.state !== "signed-in") return;

    let active = true;

    async function fetchIncident() {
      try {
        const record = await load();
        if (active) applyIncident(record);
      } catch (failure) {
        if (active) setError(describeApiFailure(failure));
      }
    }

    void fetchIncident();
    return () => {
      active = false;
    };
  }, [account.state, applyIncident, load]);

  async function update(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiWrite<Incident>(`incidents/${encodeURIComponent(params.id)}`, "PATCH", { title, description, impact_notes: impact, status });
      const record = await load();
      applyIncident(record);
    } catch (failure) {
      setError(describeApiFailure(failure));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm("Delete this incident? The record will no longer be accessible.")) return;
    setBusy(true);
    setError("");
    try {
      await apiWrite<void>(`incidents/${encodeURIComponent(params.id)}`, "DELETE");
      router.replace("/incidents");
    } catch (failure) {
      setError(describeApiFailure(failure));
      setBusy(false);
    }
  }

  if (account.state === "loading") return <p role="status">Checking your session…</p>;
  if (account.state === "error") return <p role="alert">{account.message}</p>;
  if (account.state === "signed-out") return <p>Please <Link href="/login">sign in</Link> to view incidents.</p>;
  if (error && !incident) return <p className="m1-error" role="alert">{error} <Link href="/incidents">Back to incidents</Link></p>;
  if (!incident) return <p role="status">Loading incident…</p>;

  return <section className="panel m1-form-panel" aria-labelledby="incident-detail-heading">
    <h2 id="incident-detail-heading">Incident record</h2>
    <p className="m1-hint">Created <time dateTime={incident.created_at}>{new Date(incident.created_at).toLocaleString()}</time> · {incident.environment} · {incident.severity}</p>
    <form className="m1-form" onSubmit={update}>
      <label htmlFor="detail-title">Title</label>
      <input id="detail-title" required minLength={3} maxLength={160} value={title} onChange={(event) => setTitle(event.target.value)}/>
      <label htmlFor="detail-description">Description</label>
      <textarea id="detail-description" maxLength={4000} rows={4} value={description} onChange={(event) => setDescription(event.target.value)}/>
      <label htmlFor="detail-impact">Impact notes</label>
      <textarea id="detail-impact" maxLength={4000} rows={4} value={impact} onChange={(event) => setImpact(event.target.value)}/>
      <label htmlFor="detail-status">Status</label>
      <select id="detail-status" value={status} onChange={(event) => setStatus(event.target.value as Incident["status"])}>
        <option value="open">Open</option><option value="investigating">Investigating</option><option value="resolved">Resolved</option><option value="archived">Archived</option>
      </select>
      {error && <p className="m1-error" role="alert">{error}</p>}
      <div className="m1-actions"><button className="button button-primary" type="submit" disabled={busy}>Save changes</button><button className="button m1-danger" type="button" onClick={remove} disabled={busy}>Delete incident</button><Link className="button button-outline" href={`/incidents/${encodeURIComponent(params.id)}/sources`}>Evidence &amp; sources</Link><Link className="button button-outline" href="/incidents">Back</Link></div>
    </form>
  </section>;
}
