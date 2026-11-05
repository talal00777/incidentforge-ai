"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { apiGet, apiWrite, describeApiFailure } from "@/lib/api-client";
import { availableProviders, canInvestigate, firstModel, type ProviderOption } from "@/lib/investigation-options";
import { distinctHypothesisChecks, hypothesisStatus, mergeSuggestedActions, readableInvestigationDate, type TimeDisplay } from "@/lib/investigation-presentation";
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
  const [timeDisplay, setTimeDisplay] = useState<TimeDisplay>("local");
  const evidenceRef = useRef<HTMLElement | null>(null);
  const evidenceTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const enabledProviders = useMemo(() => availableProviders(providers), [providers]);
  const visibleActions = useMemo(() => mergeSuggestedActions(report?.report.suggested_actions ?? []), [report]);
  const actionTexts = useMemo(() => visibleActions.map((item) => item.action), [visibleActions]);

  useEffect(() => {
    if (selectedEvidence) evidenceRef.current?.focus();
  }, [selectedEvidence, snapshot]);

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
      setSelectedEvidence(null);
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
      setSelectedEvidence(null);
      setReport(result);
    } catch (failure) {
      setError(describeApiFailure(failure));
    } finally {
      setWorking(false);
    }
  }

  function references(ids: string[]) {
    if (!ids.length) return <span className={styles.muted}>No supporting events cited</span>;
    return <span className={styles.references}>{ids.map((id) => (
      <button
        key={id}
        type="button"
        onClick={(event) => { evidenceTriggerRef.current = event.currentTarget; setSelectedEvidence(id); }}
        title={`Inspect event ${id}`}
        aria-label={`Inspect evidence event ${id}`}
        aria-pressed={selectedEvidence === id}
      >
        Event {id.slice(0, 8)}
      </button>
    ))}</span>;
  }

  const currentEvidence =
  snapshot && report && snapshot.id === report.snapshot_id
    ? snapshot.entries.find((item) => item.event_id === selectedEvidence)
    : undefined;

  return <main className={styles.root}>
    <header className={styles.header}>
      <h1>AI investigation</h1>
      <div className={styles.headerActions}>
        <div className={styles.timeToggle} role="group" aria-label="Date and time display">
          <button type="button" aria-pressed={timeDisplay === "local"} onClick={() => setTimeDisplay("local")}>Local</button>
          <button type="button" aria-pressed={timeDisplay === "utc"} onClick={() => setTimeDisplay("utc")}>UTC</button>
        </div>
        <Link className={styles.back} href={`/incidents/${encodeURIComponent(incidentId)}/evidence-snapshots`}>Evidence selection</Link>
      </div>
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
                {snapshots.map((item) => <option key={item.id} value={item.id}>{item.event_count} events · {readableInvestigationDate(item.created_at, timeDisplay)}</option>)}
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
                <strong>{item.model_id}</strong><span>{item.provider} · {readableInvestigationDate(item.created_at, timeDisplay)}</span>
              </button>
            </li>)}
          </ul>}
        </section>
      </div>
      {report && <section className={styles.report} aria-labelledby="report-title">
        <div className={styles.reportHeader}>
          <div>
            <span className={styles.reportType}>AI-generated investigation</span>
            <h2 id="report-title">Investigation findings</h2>
            <span>{report.provider} · {report.model_id} · {readableInvestigationDate(report.created_at, timeDisplay)}</span>
          </div>
          <span className={styles.reviewLabel}>Review required</span>
        </div>
        <div className={styles.reportBody}>
          <section className={styles.overview} aria-labelledby="overview-title">
            <h3 id="overview-title">Incident overview</h3>
            <p className={styles.summary}>{report.report.incident_summary}</p>
          </section>
          <section className={styles.reportSection} aria-labelledby="facts-title">
            <div className={styles.sectionHeading}>
              <h3 id="facts-title">Observed facts</h3>
              <span>{report.report.observed_facts.length}</span>
            </div>
            <ol className={styles.factList}>{report.report.observed_facts.map((fact, index) => <li key={index}>
              <p>{fact.statement}</p>
              <div className={styles.evidenceGroup}><strong>Source events</strong>{references(fact.event_ids)}</div>
            </li>)}</ol>
          </section>
          <section className={styles.reportSection} aria-labelledby="hypotheses-title">
            <div className={styles.sectionHeading}>
              <h3 id="hypotheses-title">Hypotheses</h3>
              <span>{report.report.hypotheses.length}</span>
            </div>
            <div className={styles.hypotheses}>
              {report.report.hypotheses.map((item, index) => {
                const assessment = hypothesisStatus(item.status);
                const additionalChecks = distinctHypothesisChecks(item.further_checks, actionTexts);
                return <article key={index}>
                  <div className={styles.hypothesisHeading}>
                    <h4>{item.title}</h4>
                    <span className={styles.assessment} title={assessment.meaning} aria-label={assessment.meaning}>
                      {assessment.label}
                    </span>
                  </div>
                  <div className={styles.evidenceRows}>
                    <div className={styles.citedLine}><strong>Supporting evidence</strong>{references(item.supporting_event_ids)}</div>
                    {item.contradicting_event_ids.length > 0 && <div className={styles.citedLine}><strong>Contradicting evidence</strong>{references(item.contradicting_event_ids)}</div>}
                  </div>
                  {item.alternative_explanations.length > 0 && <div className={styles.hypothesisDetail}>
                    <strong>Other possibilities</strong>
                    <ul>{item.alternative_explanations.map((alternative, i) => <li key={i}>{alternative}</li>)}</ul>
                  </div>}
                  {additionalChecks.length > 0 && <div className={styles.hypothesisDetail}>
                    <strong>Additional checks</strong>
                    <ul>{additionalChecks.map((check, i) => <li key={i}>{check}</li>)}</ul>
                  </div>}
                </article>;
              })}
            </div>
          </section>
          {visibleActions.length > 0 && <section className={styles.reportSection} aria-labelledby="checks-title">
            <div className={styles.sectionHeading}>
              <h3 id="checks-title">Suggested checks</h3>
              <span>{visibleActions.length}</span>
            </div>
            <ol className={styles.factList}>{visibleActions.map((item, index) => <li key={index}>
              <p>{item.action}</p>
              <div className={styles.evidenceGroup}><strong>Related events</strong>{references(item.rationale_event_ids)}</div>
            </li>)}</ol>
          </section>}
          {report.report.limitations.length > 0 && <section className={styles.reportSection} aria-labelledby="limits-title">
            <div className={styles.sectionHeading}><h3 id="limits-title">Limitations</h3></div>
            <ul className={styles.limitations}>{report.report.limitations.map((item, i) => <li key={i}>{item}</li>)}</ul>
          </section>}
          {selectedEvidence && <aside className={styles.evidenceFocus} ref={evidenceRef} tabIndex={-1} role="region" aria-labelledby="evidence-focus-title">
            <div className={styles.focusHeader}>
              <h3 id="evidence-focus-title">Source event</h3>
              <button type="button" onClick={() => { setSelectedEvidence(null); evidenceTriggerRef.current?.focus(); }}>Close</button>
            </div>
            {currentEvidence ? <>
              <p className={styles.eventContext}>{currentEvidence.service || "Unknown service"} · {currentEvidence.severity || "Unknown severity"}</p>
              <dl className={styles.eventMetadata}>
                <div><dt>Source</dt><dd>{currentEvidence.source_name}</dd></div>
                <div><dt>Lines</dt><dd>{currentEvidence.source_lines[0]}–{currentEvidence.source_lines[1]}</dd></div>
                <div><dt>Time</dt><dd>{readableInvestigationDate(currentEvidence.occurred_at, timeDisplay)}</dd></div>
                <div><dt>Event ID</dt><dd className={styles.fullId}>{currentEvidence.event_id}</dd></div>
              </dl>
              <p className={styles.eventMessage}>{currentEvidence.message}</p>
            </> : <p className={styles.muted}>Source event not available in this snapshot.</p>}
          </aside>}
        </div>
      </section>}
    </>}
  </main>;
}
