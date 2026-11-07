"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ChangeEvent } from "react";

import { apiGet, apiWrite, describeApiFailure } from "@/lib/api-client";
import { humanReviewPath, investigationReportPath } from "@/lib/investigation-routes";
import { postmortemVersionPath } from "@/lib/postmortem-routes";
import {
  isFinalizedReview,
  type InvestigationSummary,
  type PostmortemSummary,
  type PostmortemVersion,
  type SavedReview,
} from "@/lib/postmortem-types";
import styles from "./postmortem.module.css";

function readableDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown date" : `${date.toLocaleString()} (local)`;
}

export function PostmortemWorkspace({ incidentId }: { incidentId: string }) {
  const router = useRouter();
  const root = `incidents/${encodeURIComponent(incidentId)}`;
  const [reports, setReports] = useState<PostmortemSummary[]>([]);
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [review, setReview] = useState<SavedReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      apiGet<PostmortemSummary[]>(`${root}/reports`),
      apiGet<InvestigationSummary[]>(`${root}/investigations`),
    ]).then(([versions, results]) => {
      if (!active) return;
      setReports(versions);
      setInvestigations(results);
      if (results[0]) {
        setReview(null);
        setReviewLoading(true);
        setSelected(results[0].id);
      }
    }).catch((failure: unknown) => {
      if (active) setError(describeApiFailure(failure));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [root]);

  useEffect(() => {
    if (!selected) return; 
    let active = true;
    apiGet<SavedReview>(`${root}/investigations/${encodeURIComponent(selected)}/review`)
      .then((value) => { if (active) setReview(value); })
      .catch((failure: unknown) => { if (active) setError(describeApiFailure(failure)); })
      .finally(() => { if (active) setReviewLoading(false); });
    return () => { active = false; };
  }, [root, selected]);

  async function finalize() {
    if (!selected || !isFinalizedReview(review) || saving || !review) return;
    setSaving(true);
    setError("");
    try {
      const saved = await apiWrite<PostmortemVersion>(`${root}/reports`, "POST", {
        investigation_id: selected,
        expected_review_revision: review.revision,
      });
      router.push(postmortemVersionPath(incidentId, saved.id));
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    } finally {
      setSaving(false);
    }
  }

  return <main className={styles.page}>
    <nav aria-label="Breadcrumb" className={styles.breadcrumbs}>
      <Link href="/">Home</Link><span aria-hidden="true">/</span>
      <Link href={`/incidents/${encodeURIComponent(incidentId)}`}>Incident</Link>
      <span aria-hidden="true">/</span><span aria-current="page">Postmortems</span>
    </nav>
    <div className={styles.heading}>
      <div>
        <p className={styles.eyebrow}>Incident reporting</p>
        <h1>Postmortems</h1>
        <p className={styles.muted}>Reviewed, versioned records of incident findings.</p>
      </div>
      <Link className={styles.secondary} href={`/incidents/${encodeURIComponent(incidentId)}/investigations`}>AI investigations</Link>
    </div>

    {error && <p className={styles.error} role="alert">{error}</p>}
    {loading ? <p role="status" className={styles.muted}>Loading postmortems…</p> : <div className={styles.grid}>
      <section className={styles.card} aria-labelledby="create-postmortem-title">
        <h2 id="create-postmortem-title">Finalize a review</h2>
        <p className={styles.muted}>Create a frozen version from a completed human review.</p>
        <label className={styles.field}>AI investigation
          <select
            value={selected}
            onChange={(event: ChangeEvent<HTMLSelectElement>) => {
              const next = event.target.value;
              setSelected(next);
              setReview(null);
              setReviewLoading(Boolean(next));
              setError("");
            }}
            disabled={saving}
          >
            {investigations.length === 0 && <option value="">No saved investigations</option>}
            {investigations.map((item) => <option key={item.id} value={item.id}>{readableDate(item.created_at)} · {item.model_id}</option>)}
          </select>
        </label>
        {reviewLoading ? <p className={styles.muted} role="status">Checking review…</p> : review && <div className={styles.reviewStatus}>
          <span className={isFinalizedReview(review) ? styles.good : styles.pending}>{isFinalizedReview(review) ? "Ready to finalize" : "Review incomplete"}</span>
          <span className={styles.muted}>Review revision {review.revision}</span>
        </div>}
        {selected && !reviewLoading && !isFinalizedReview(review) && <Link href={humanReviewPath(incidentId, selected)}>Complete human review</Link>}
        <button type="button" className={styles.primary} disabled={!isFinalizedReview(review) || saving || reviewLoading} onClick={() => void finalize()}>
          {saving ? "Finalizing…" : "Create report version"}
        </button>
        {selected && <Link className={styles.minor} href={investigationReportPath(incidentId, selected)}>View AI findings</Link>}
      </section>

      <section className={styles.card} aria-labelledby="history-title">
        <div className={styles.sectionHead}><h2 id="history-title">Version history</h2><span className={styles.muted}>{reports.length} shown</span></div>
        {reports.length === 0 ? <p className={styles.muted}>No finalized postmortems yet.</p> : <ol className={styles.versionList}>
          {reports.map((item) => <li key={item.id}>
            <Link href={postmortemVersionPath(incidentId, item.id)}>
              <span className={styles.versionName}>Version {item.version}</span>
              <span className={styles.muted}>{readableDate(item.created_at)}</span>
              <span className={styles.muted}>Human review revision {item.review_revision_number}</span>
            </Link>
          </li>)}
        </ol>}
      </section>
    </div>}
  </main>;
}
