"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiGet, describeApiFailure } from "@/lib/api-client";
import { investigationReportPath } from "@/lib/investigation-routes";
import { postmortemsPath } from "@/lib/postmortem-routes";
import type { PostmortemVersion, SourceReference } from "@/lib/postmortem-types";
import { PostmortemExports } from "./postmortem-exports";
import styles from "./postmortem.module.css";

function formattedDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unknown" : `${date.toLocaleString()} (local)`;
}

function citedEvents(ids: string[], sources: SourceReference[], sourceHref: string) {
  if (!ids.length) return <span className={styles.muted}>None cited</span>;
  return <span className={styles.citations}>{ids.map((id) => {
    const source = sources.find((item) => item.event_id === id);
    return <Link key={id} href={sourceHref} title={`Open source investigation for event ${id}`} className={styles.citation}>
      {source?.service || "Event"} · {id.slice(0, 8)}
    </Link>;
  })}</span>;
}

export function PostmortemDetail({ incidentId, versionId }: { incidentId: string; versionId: string }) {
  const [version, setVersion] = useState<PostmortemVersion | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const root = `incidents/${encodeURIComponent(incidentId)}/reports/${encodeURIComponent(versionId)}`;

  useEffect(() => {
    let active = true;
    apiGet<PostmortemVersion>(root)
      .then((result) => { if (active) setVersion(result); })
      .catch((failure: unknown) => { if (active) setError(describeApiFailure(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [root]);

  const doc = version?.content;
  const findings = doc?.ai.findings;
  const sourceHref = doc ? investigationReportPath(incidentId, doc.ai.investigation_id) : "";
  return <main className={styles.page}>
    <nav aria-label="Breadcrumb" className={styles.breadcrumbs}>
      <Link href="/">Home</Link><span aria-hidden="true">/</span>
      <Link href={`/incidents/${encodeURIComponent(incidentId)}`}>Incident</Link>
      <span aria-hidden="true">/</span>
      <Link href={postmortemsPath(incidentId)}>Postmortems</Link>
      <span aria-hidden="true">/</span><span aria-current="page">Version</span>
    </nav>
    {error && <p className={styles.error} role="alert">{error}</p>}
    {loading ? <p role="status" className={styles.muted}>Loading report…</p> : !doc || !findings || !version ? <p className={styles.muted}>Report unavailable.</p> : <>
      <header className={styles.heading}>
        <div>
          <p className={styles.eyebrow}>Finalized incident postmortem · Version {version.version}</p>
          <h1>{doc.incident.title}</h1>
          <p className={styles.muted}>Created {formattedDate(version.created_at)} · Review revision {version.review_revision_number}</p>
        </div>
        <Link className={styles.secondary} href={investigationReportPath(incidentId, doc.ai.investigation_id)}>View source investigation</Link>
      </header>
      <PostmortemExports incidentId={incidentId} versionId={versionId} />
      <div className={styles.document}>
        <section className={styles.block} aria-labelledby="summary-title">
          <div className={styles.sectionHead}><h2 id="summary-title">Incident summary</h2><span className={styles.origin}>AI-generated</span></div>
          <p className={styles.summary}>{findings.incident_summary}</p>
        </section>

        <section className={styles.block} aria-labelledby="timeline-title">
          <div className={styles.sectionHead}><h2 id="timeline-title">Evidence timeline</h2><span className={styles.origin}>Recorded events</span></div>
          <ol className={styles.readableList}>
            {doc.timeline.map((event) => <li key={event.event_id}>
              <strong>{event.occurred_at ? formattedDate(event.occurred_at) : "Time unknown"}</strong>
              <span> · {event.service || "Unknown service"} · {event.severity || "Unknown severity"}</span>
              {citedEvents([event.event_id], doc.evidence_manifest, sourceHref)}
            </li>)}
          </ol>
        </section>

        <section className={styles.block} aria-labelledby="observations-title">
          <div className={styles.sectionHead}><h2 id="observations-title">Observed facts</h2><span className={styles.origin}>AI-generated</span></div>
          {findings.observed_facts.length === 0 ? <p className={styles.muted}>No facts recorded.</p> : <ol className={styles.readableList}>
            {findings.observed_facts.map((fact, index) => <li key={index}>
              <p>{fact.statement}</p>
              {citedEvents(fact.event_ids, doc.evidence_manifest, sourceHref)}
            </li>)}
          </ol>}
        </section>

        <section className={styles.block} aria-labelledby="hypotheses-title">
          <div className={styles.sectionHead}><h2 id="hypotheses-title">Hypotheses and human decisions</h2><span className={styles.origin}>AI + Human</span></div>
          {findings.hypotheses.length === 0 ? <p className={styles.muted}>No hypotheses recorded.</p> : <div className={styles.hypotheses}>
            {findings.hypotheses.map((hypothesis, index) => {
              const decision = doc.human.hypotheses.find((item) => item.index === index);
              return <article key={index} className={styles.hypothesis}>
                <div className={styles.sectionHead}><h3>{index + 1}. {hypothesis.title}</h3><span className={styles.origin}>AI: {hypothesis.status.replaceAll("_", " ")}</span></div>
                <p><strong>Human decision:</strong> {decision?.decision.replaceAll("_", " ") || "Not recorded"}</p>
                {decision?.note && <p className={styles.note}>{decision.note}</p>}
                <div className={styles.citationGroup}>
                  <strong>Supporting events</strong>
                  {citedEvents(hypothesis.supporting_event_ids, doc.evidence_manifest, sourceHref)}
                </div>
                {hypothesis.contradicting_event_ids.length > 0 && <div className={styles.citationGroup}>
                  <strong>Contradicting events</strong>
                  {citedEvents(hypothesis.contradicting_event_ids, doc.evidence_manifest, sourceHref)}
                </div>}
                {hypothesis.alternative_explanations.length > 0 && <div className={styles.inlineSection}>
                  <strong>Alternatives</strong>
                  <ul>{hypothesis.alternative_explanations.map((item, i) => <li key={i}>{item}</li>)}</ul>
                </div>}
              </article>;
            })}
          </div>}
        </section>

        <section className={styles.block} aria-labelledby="assessment-title">
          <div className={styles.sectionHead}><h2 id="assessment-title">Human assessment</h2><span className={styles.origin}>Human-authored</span></div>
          <div className={styles.assessment}>
            <div><h3>Impact</h3><p>{doc.human.impact_notes || "Not recorded"}</p></div>
            <div><h3>Remediation</h3><p>{doc.human.remediation_notes || "Not recorded"}</p></div>
          </div>
        </section>

        <section className={styles.block} aria-labelledby="checks-title">
          <div className={styles.sectionHead}><h2 id="checks-title">Suggested checks</h2><span className={styles.origin}>AI-generated</span></div>
          {findings.suggested_actions.length === 0 ? <p className={styles.muted}>None recorded.</p> : <ol className={styles.readableList}>
            {findings.suggested_actions.map((item, index) => <li key={index}>
              <p>{item.action}</p>
              {citedEvents(item.rationale_event_ids, doc.evidence_manifest, sourceHref)}
            </li>)}
          </ol>}
        </section>

        {findings.limitations.length > 0 && <section className={styles.block} aria-labelledby="limitations-title">
          <div className={styles.sectionHead}><h2 id="limitations-title">Limitations</h2><span className={styles.origin}>AI-generated</span></div>
          <ul className={styles.readableList}>{findings.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>
        </section>}

        <details className={styles.provenance}>
          <summary>Source provenance and version metadata</summary>
          <dl className={styles.metadata}>
            <div><dt>Evidence source</dt><dd>{doc.ai.evidence_snapshot.id}</dd></div>
            <div><dt>AI provider / model</dt><dd>{doc.ai.provider} / {doc.ai.model_id}</dd></div>
            <div><dt>Prompt</dt><dd>{doc.ai.prompt_profile} · {doc.ai.prompt_version}</dd></div>
            <div><dt>Content checksum</dt><dd className={styles.breakWord}>{version.content_sha256}</dd></div>
            <div><dt>Evidence checksum</dt><dd className={styles.breakWord}>{doc.ai.evidence_snapshot.sha256}</dd></div>
            <div><dt>Reviewer</dt><dd>{doc.human.author_id}</dd></div>
          </dl>
          <h3>Event sources</h3>
          <ul className={styles.readableList}>{doc.evidence_manifest.map((entry) => <li key={entry.event_id}>
            {entry.source_name} · lines {entry.source_lines.join("–")} · {entry.event_id.slice(0, 8)}
          </li>)}</ul>
        </details>
      </div>
    </>}
  </main>;
}
