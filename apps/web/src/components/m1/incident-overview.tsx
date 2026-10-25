"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, IncidentPage, apiGet, describeApiFailure } from "@/lib/api-client";
import { IncidentTable } from "@/components/m1/incident-table";
import { useAccount } from "@/components/m1/use-account";

export function IncidentOverview() {
  const account = useAccount();
  const [pages, setPages] = useState<IncidentPage[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (account.state !== "signed-in") return;
    let active = true;
    Promise.all([
      apiGet<IncidentPage>("incidents?page_size=5"),
      apiGet<IncidentPage>("incidents?status=open&page_size=1"),
      apiGet<IncidentPage>("incidents?status=investigating&page_size=1"),
    ]).then((value) => { if (active) setPages(value); })
      .catch((failure: unknown) => {
        if (active) setError(failure instanceof ApiError ? failure.message : describeApiFailure(failure));
      });
    return () => { active = false; };
  }, [account.state]);

  if (account.state === "loading") return <p role="status">Loading workspace…</p>;
  if (account.state === "error") return <p role="alert">{account.message}</p>;
  if (account.state === "signed-out") return <section className="panel m1-prompt"><h2>Your incidents</h2><p>Sign in to access your incident records.</p><Link className="button button-primary" href="/login">Sign in</Link></section>;
  if (error) return <p role="alert" className="m1-error">{error}</p>;
  if (!pages) return <p role="status">Loading incidents…</p>;
  const [all, open, investigating] = pages;
  return <>
    <section className="metric-grid" aria-label="Incident summary">
      {[
        { label: "All incidents", count: all.count },
        { label: "Open incidents", count: open.count },
        { label: "Investigating", count: investigating.count },
      ].map((metric) => <article className="metric-card" key={metric.label}><h2>{metric.label}</h2><p className="metric-value">{metric.count}</p></article>)}
    </section>
    <section className="panel incidents-panel" aria-labelledby="incidents-heading">
      <div className="panel-header panel-header-with-actions"><div><h2 id="incidents-heading">Recent incidents</h2><p>Incidents in your workspace.</p></div><Link href="/incidents" className="button button-outline">View all</Link></div>
      <IncidentTable incidents={all.results} />
    </section>
  </>;
}
