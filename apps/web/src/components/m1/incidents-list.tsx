"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { IncidentPage, apiGet, describeApiFailure } from "@/lib/api-client";
import { IncidentTable } from "@/components/m1/incident-table";
import { AccountSection } from "@/components/m1/account-section";
import { useAccount } from "@/components/m1/use-account";

const statuses = ["all", "open", "investigating", "resolved", "archived"] as const;

type ListState = { key: string; data?: IncidentPage; error?: string };

export function IncidentsList() {
  const account = useAccount();
  const [status, setStatus] = useState<(typeof statuses)[number]>("all");
  const [page, setPage] = useState(1);
  const [draftSearch, setDraftSearch] = useState("");
  const [search, setSearch] = useState("");
  const [retryCount, setRetryCount] = useState(0);
  const [response, setResponse] = useState<ListState | null>(null);
  const key = JSON.stringify([status, page, search, retryCount]);
  const current = response?.key === key ? response : null;

  useEffect(() => {
    if (account.state !== "signed-in") return;
    let active = true;
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (status !== "all") params.set("status", status);
    if (search) params.set("search", search);
    apiGet<IncidentPage>(`incidents?${params}`)
      .then((data) => { if (active) setResponse({ key, data }); })
      .catch((failure: unknown) => {
        if (active) setResponse({ key, error: describeApiFailure(failure) });
      });
    return () => { active = false; };
  }, [account.state, status, page, search, key]);

  if (account.state !== "signed-in") return <AccountSection />;

  return <>
    <div className="m1-toolbar"><AccountSection /><Link className="button button-primary" href="/incidents/new">New incident</Link></div>
    <section className="panel" aria-labelledby="list-heading">
      <div className="panel-header"><div><h2 id="list-heading">Incidents</h2><p>Records owned by your account.</p></div>
        <label className="m1-filter">Status
          <select value={status} onChange={(event) => { setStatus(event.target.value as typeof status); setPage(1); }}>
            {statuses.map((item) => <option key={item} value={item}>{item === "all" ? "All statuses" : item}</option>)}
          </select>
        </label>
      </div>
      <form role="search" aria-label="Search incidents" className="m1-toolbar" onSubmit={(event) => {
        event.preventDefault();
        setSearch(draftSearch.trim());
        setPage(1);
      }}>
        <label htmlFor="incident-search">Search title, service or description</label>
        <input id="incident-search" type="search" maxLength={100} value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)} />
        <button type="submit">Search</button>
        {search && <button type="button" onClick={() => { setDraftSearch(""); setSearch(""); setPage(1); }}>Clear</button>}
      </form>
      {current?.error ? <p className="m1-error" role="alert">{current.error} <button type="button" onClick={() => setRetryCount((count) => count + 1)}>Retry</button></p> : current?.data ? <><IncidentTable incidents={current.data.results}/><div className="m1-pagination"><span>{current.data.count} incidents</span><button type="button" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page}</span><button type="button" disabled={page * 20 >= current.data.count} onClick={() => setPage(page + 1)}>Next</button></div></> : <p role="status" className="m1-empty">Loading incidents…</p>}
    </section>
  </>;
}
