"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Incident, IncidentInput, apiWrite, describeApiFailure } from "@/lib/api-client";
import { useAccount } from "@/components/m1/use-account";

export function CreateIncident() {
  const account = useAccount();
  const router = useRouter();
  const [values, setValues] = useState<IncidentInput>({
    title: "", description: "", service_name: "", environment: "production", timezone: "UTC", severity: "medium",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const incident = await apiWrite<Incident>("incidents", "POST", values);
      router.push(`/incidents/${incident.id}`);
    } catch (failure) {
      setError(describeApiFailure(failure));
    } finally {
      setBusy(false);
    }
  }

  if (account.state === "loading") return <p role="status">Checking your session…</p>;
  if (account.state === "error") return <p role="alert">{account.message}</p>;
  if (account.state === "signed-out") return <p>Please <Link href="/login">sign in</Link> to create incidents.</p>;

  return <section className="panel m1-form-panel" aria-labelledby="form-title">
    <h2 id="form-title">Incident details</h2>
    <form className="m1-form" onSubmit={submit}>
      <label htmlFor="incident-title">Title</label>
      <input id="incident-title" maxLength={160} minLength={3} required value={values.title} onChange={(event) => setValues({ ...values, title: event.target.value })}/>
      <label htmlFor="incident-service">Service</label>
      <input id="incident-service" maxLength={120} value={values.service_name} onChange={(event) => setValues({ ...values, service_name: event.target.value })}/>
      <label htmlFor="incident-severity">Severity</label>
      <select id="incident-severity" value={values.severity} onChange={(event) => setValues({ ...values, severity: event.target.value as IncidentInput["severity"] })}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select>
      <label htmlFor="incident-environment">Environment</label>
      <select id="incident-environment" value={values.environment} onChange={(event) => setValues({ ...values, environment: event.target.value as IncidentInput["environment"] })}><option value="production">Production</option><option value="staging">Staging</option><option value="development">Development</option><option value="other">Other</option></select>
      <label htmlFor="incident-timezone">Timezone (IANA)</label>
      <input id="incident-timezone" required maxLength={64} value={values.timezone} onChange={(event) => setValues({ ...values, timezone: event.target.value })}/>
      <label htmlFor="incident-description">Description</label>
      <textarea id="incident-description" maxLength={4000} rows={4} value={values.description} onChange={(event) => setValues({ ...values, description: event.target.value })}/>
      {error && <p className="m1-error" role="alert">{error}</p>}
      <div className="m1-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Creating…" : "Create incident"}</button><Link href="/incidents" className="button button-outline">Cancel</Link></div>
    </form>
  </section>;
}
