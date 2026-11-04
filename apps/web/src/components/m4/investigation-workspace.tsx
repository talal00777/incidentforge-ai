"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiGet, apiWrite, describeApiFailure } from "@/lib/api-client";
import { availableProviders, canInvestigate, firstModel, type ProviderOption } from "@/lib/investigation-options";
import styles from "./investigation-workspace.module.css";

type EvidenceEntry = {
  event_id: string;
  source_id: string;
  source_name: string;
  source_lines: [number, number];
  occurred_at: string | null;
  severity: string;
  service: string;
  message: string;
};
type Snapshot = {
  id: string;
  sha256: string;
  event_count: number;
  payload_bytes: number;
  created_at: string;
  entries: EvidenceEntry[];
};
type SnapshotSummary = Omit<Snapshot, "entries">;
type Fact = { statement: string; event_ids: string[] };
type Hypothesis = {
  title: string;
  status: string;
  supporting_event_ids: string[];
  contradicting_event_ids: string[];
  alternative_explanations: string[];
  further_checks: string[];
};
type Action = { action: string; safety: string; rationale_event_ids: string[] };
type ReportBody = {
  schema_version: string;
  incident_summary: string;
  observed_facts: Fact[];
  hypotheses: Hypothesis[];
  suggested_actions: Action[];
  limitations: string[];
};
type ReportSummary = {
  id: string;
  snapshot_id: string;
  provider: string;
  model_id: string;
  temperature: number;
  max_output_tokens: number;
  prompt_profile: string;
  created_at: string;
};
type Report = ReportSummary & { report: ReportBody };
type PromptProfile = "zero_shot" | "few_shot" | "decomposed_verified";

function readableDate(value: string): string {
  const time = new Date(value);
  return Number.isNaN(time.valueOf()) ? "Time unknown" : new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(time);
}

export function InvestigationWorkspace({ incidentId }: { incidentId: string }) {
  const root = `incidents/${encodeURIComponent(incidentId)}`;
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [history, setHistory] = useState<ReportSummary[]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [temperature, setTemperature] = useState("0.2");
  const [maxTokens, setMaxTokens] = useState("2048");
  const [profile, setProfile] = useState<PromptProfile>("decomposed_verified");
  const [consented, setConsented] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const enabledProviders = useMemo(() => availableProviders(providers), [providers]);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiGet<ProviderOption[]>("investigation/providers"),
      apiGet<SnapshotSummary[]>(`${root}/evidence/snapshots`),
      apiGet<ReportSummary[]>(`${root}/investigations`),
    ]).then(([options, evidence, reports]) => {
      if (!active) return;
      setProviders(options);
      setSnapshots(evidence);
      setHistory(reports);
      const first = availableProviders(options)[0];
      if (first) {
        setProvider(first.name);
        setModel(first.models[0]);
      }
      if (evidence[0]) setSnapshotId(evidence[0].id);
    }).catch((failure: unknown) => {
      if (active) setError(describeApiFailure(failure));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [root]);

  useEffect(() => {
    if (!snapshotId) return;
    let active = true;
    apiGet<Snapshot>(`${root}/evidence/snapshots/${encodeURIComponent(snapshotId)}`)
      .then((result) => { if (active) setSnapshot(result); })
      .catch((failure: unknown) => { if (active) setError(describeApiFailure(failure)); });
    return () => { active = false; };
  }, [root, snapshotId]);

  function changeSnapshot(id: string) {
    setSnapshotId(id);
    setSnapshot(null);
    setConsented(false);
    setReport(null);
    setSelectedEvidence(null);
    setError("");
  }

  async function generateReport() {
    if (!snapshot || snapshot.id !== snapshotId || !canInvestigate(snapshotId, provider, model, consented, working)) return;
    setWorking(true);
    setConsented(false);
    setReport(null);
    setError("");
    try {
      const result = await apiWrite<Report>(`${root}/investigations`, "POST", {
        snapshot_id: snapshot.id,
        provider,
        model_id: model,
        temperature: Number(temperature),
        max_output_tokens: Number(maxTokens),
        prompt_profile: profile,
        transmission_consent: { accepted: true, snapshot_sha256: snapshot.sha256 },
      });
      setReport(result);
      setHistory(await apiGet<ReportSummary[]>(`${root}/investigations`));
    } catch (failure) {
      setError(describeApiFailure(failure));
    } finally {
      setWorking(false);
    }
  }

  async function openReport(id: string) {
    setWorking(true);
    setError("");
    try {
      const result = await apiGet<Report>(`${root}/investigations/${encodeURIComponent(id)}`);
      if (result.snapshot_id !== snapshotId) changeSnapshot(result.snapshot_id);
      setReport(result);
    } catch (failure) {
      setError(describeApiFailure(failure));
    } finally {
      setWorking(false);
    }
  }

  function references(ids: string[]) {
    if (!ids.length) return <span className={styles.muted}>None cited</span>;
    return <span className={styles.references}>{ids.map((id) => (
      <button key={id} type="button" onClick={() => setSelectedEvidence(id)} title={id}>
        {id.slice(0, 8)}
      </button>
    ))}</span>;
  }

  const currentEvidence = snapshot?.entries.find((item) => item.event_id === selectedEvidence);

  return <main className={styles.root}>
    <header className={styles.header}>
      <h1>AI investigation</h1>
      <Link className={styles.back} href={`/incidents/${encodeURIComponent(incidentId)}/evidence-snapshots`}>Evidence selection</Link>
    </header>

    {error && <p className={styles.error} role="alert">{error}</p>}
    {loading ? <p className={styles.empty} role="status">Loading investigations…</p> : <>
      <div className={styles.columns}>
        <section className={styles.card} aria-labelledby="settings-title">
          <div className={styles.cardHeader}><h2 id="settings-title">Investigation settings</h2></div>
          <div className={styles.form}>
            <label>Evidence snapshot
              <select value={snapshotId} onChange={(event) => changeSnapshot(event.target.value)} disabled={working}>
                {snapshots.length === 0 && <option value="">No saved snapshots</option>}
                {snapshots.map((item) => <option key={item.id} value={item.id}>{item.event_count} events · {readableDate(item.created_at)}</option>)}
              </select>
            </label>
            <div className={styles.inputRow}>
              <label>Provider
                <select value={provider} onChange={(event) => {
                  const value = event.target.value;
                  setProvider(value);
                  setModel(firstModel(providers, value));
                  setConsented(false);
                }} disabled={working || !enabledProviders.length}>
                  {enabledProviders.length === 0 && <option value="">Not configured</option>}
                  {enabledProviders.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
                </select>
              </label>
              <label>Model
                <select value={model} onChange={(event) => { setModel(event.target.value); setConsented(false); }} disabled={working || !provider}>
                  {(enabledProviders.find((item) => item.name === provider)?.models ?? []).map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className={styles.inputRow}>
              <label>Temperature
                <select value={temperature} onChange={(event) => { setTemperature(event.target.value); setConsented(false); }} disabled={working}>
                  <option value="0">0.0</option><option value="0.2">0.2</option><option value="0.7">0.7</option>
                </select>
              </label>
              <label>Output tokens
                <select value={maxTokens} onChange={(event) => { setMaxTokens(event.target.value); setConsented(false); }} disabled={working}>
                  <option value="512">512</option><option value="1024">1024</option><option value="2048">2048</option><option value="4096">4096</option>
                </select>
              </label>
            </div>
            <label>Prompt profile
              <select value={profile} onChange={(event) => { setProfile(event.target.value as PromptProfile); setConsented(false); }} disabled={working}>
                <option value="decomposed_verified">Evidence-first + verification</option>
                <option value="few_shot">Few-shot examples</option>
                <option value="zero_shot">Zero-shot baseline</option>
              </select>
            </label>
            {snapshot && snapshot.id === snapshotId && <div className={styles.snapshotPreview}>
              <strong>{snapshot.event_count} selected events</strong>
              <span>{(snapshot.payload_bytes / 1024).toFixed(1)} KB · Redacted evidence</span>
              <details>
                <summary>Review data to be sent</summary>
                <ol>{snapshot.entries.map((item) => <li key={item.event_id}>
                  <span>{item.service || "Unknown service"} · {item.source_name} · lines {item.source_lines.join("–")}</span>
                  <p>{item.message}</p>
                </li>)}</ol>
              </details>
            </div>}
            <label className={styles.consent}>
              <input type="checkbox" checked={consented} onChange={(event) => setConsented(event.target.checked)} disabled={working || !snapshot || snapshot.id !== snapshotId || !model}/>
              <span>I consent to sending this selected, redacted snapshot to {provider || "the selected provider"} for this investigation only.</span>
            </label>
            <button type="button" className={styles.primary} disabled={!snapshot || snapshot.id !== snapshotId || !canInvestigate(snapshotId, provider, model, consented, working)} onClick={() => void generateReport()}>
              {working ? "Processing…" : "Generate investigation"}
            </button>
          </div>
        </section>
        <section className={styles.card} aria-labelledby="history-title">
          <div className={styles.cardHeader}><h2 id="history-title">Previous investigations</h2><span>{history.length}</span></div>
          {history.length === 0 ? <p className={styles.empty}>No investigations yet</p> : <ul className={styles.history}>
            {history.map((item) => <li key={item.id}>
              <button type="button" disabled={working} onClick={() => void openReport(item.id)}>
                <strong>{item.model_id}</strong><span>{item.provider} · {readableDate(item.created_at)}</span>
              </button>
            </li>)}
          </ul>}
        </section>
      </div>
      {report && <section className={styles.report} aria-labelledby="report-title">
        <div className={styles.reportHeader}><div><h2 id="report-title">AI-generated findings</h2><span>{report.provider} · {report.model_id} · {readableDate(report.created_at)}</span></div></div>
        <div className={styles.reportBody}>
          <p className={styles.summary}>{report.report.incident_summary}</p>
          <section><h3>Observed facts</h3>
            <ul className={styles.factList}>{report.report.observed_facts.map((fact, index) => <li key={index}>
              <p>{fact.statement}</p>{references(fact.event_ids)}
            </li>)}</ul>
          </section>
          <section><h3>Hypotheses</h3><div className={styles.hypotheses}>
            {report.report.hypotheses.map((item, index) => <article key={index}>
              <div className={styles.hypothesisHeading}><h4>{item.title}</h4><span>{item.status.replaceAll("_", " ")}</span></div>
              <div className={styles.citedLine}><strong>Supporting</strong>{references(item.supporting_event_ids)}</div>
              {item.contradicting_event_ids.length > 0 && <div className={styles.citedLine}><strong>Counterevidence</strong>{references(item.contradicting_event_ids)}</div>}
              {item.alternative_explanations.length > 0 && <p><b>Alternatives:</b> {item.alternative_explanations.join(" · ")}</p>}
              {item.further_checks.length > 0 && <ul>{item.further_checks.map((check, i) => <li key={i}>{check}</li>)}</ul>}
            </article>)}
          </div></section>
          {report.report.suggested_actions.length > 0 && <section><h3>Suggested checks</h3>
            <ul className={styles.factList}>{report.report.suggested_actions.map((item, index) => <li key={index}>
              <p>{item.action}</p>{references(item.rationale_event_ids)}
            </li>)}</ul>
          </section>}
          {report.report.limitations.length > 0 && <section><h3>Limitations</h3><ul className={styles.limitations}>{report.report.limitations.map((item, i) => <li key={i}>{item}</li>)}</ul></section>}
          {selectedEvidence && <section className={styles.evidenceFocus}>
            <div className={styles.focusHeader}><h3>Evidence reference</h3><button type="button" onClick={() => setSelectedEvidence(null)}>Close</button></div>
            {currentEvidence ? <><strong>{currentEvidence.service || "Unknown service"} · {currentEvidence.source_name}</strong>
              <p>{currentEvidence.message}</p></> : <p>Choose the report snapshot to inspect this event.</p>}
          </section>}
        </div>
      </section>}
    </>}
  </main>;
}
