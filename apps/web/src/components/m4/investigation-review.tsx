"use client";

import { useEffect, useState } from "react";

import { apiGet, apiWrite, describeApiFailure } from "@/lib/api-client";
import {
  canCompleteReview,
  updateHypothesis,
  type HumanReview,
  type HumanReviewDecision,
} from "@/lib/investigation-review";
import styles from "./investigation-review.module.css";

type Props = { incidentId: string; reportId: string; hypotheses: string[] };

const decisions: { value: HumanReviewDecision; label: string }[] = [
  { value: "needs_review", label: "Needs review" },
  { value: "reviewed", label: "Reviewed — no conclusion" },
  { value: "accepted_as_working_hypothesis", label: "Accepted as working hypothesis" },
  { value: "rejected", label: "Rejected" },
];

export function InvestigationReview({ incidentId, reportId, hypotheses }: Props) {
  const endpoint = `incidents/${encodeURIComponent(incidentId)}/investigations/${encodeURIComponent(reportId)}/review`;
  const [review, setReview] = useState<HumanReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const reviewedCount = review?.hypotheses.filter((item) => item.decision !== "needs_review").length ?? 0;

  useEffect(() => {
    let active = true;
    apiGet<HumanReview>(endpoint)
      .then((value) => { if (active) setReview(value); })
      .catch((failure: unknown) => { if (active) setError(describeApiFailure(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [endpoint]);

  function change(next: HumanReview) {
    setReview(next);
    setDirty(true);
    setNotice("");
  }

  async function save() {
    if (!review || saving) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const saved = await apiWrite<HumanReview>(endpoint, "PUT", {
        expected_revision: review.revision,
        status: review.status,
        impact_notes: review.impact_notes,
        remediation_notes: review.remediation_notes,
        hypotheses: review.hypotheses,
      });
      setReview(saved);
      setDirty(false);
      setNotice("Review saved");
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    } finally {
      setSaving(false);
    }
  }

  async function reload() {
    if (saving) return;
    setLoading(true);
    setError("");
    setNotice("");
    try {
      setReview(await apiGet<HumanReview>(endpoint));
      setDirty(false);
    } catch (failure: unknown) {
      setError(describeApiFailure(failure));
    } finally {
      setLoading(false);
    }
  }

  return <section className={styles.root} aria-labelledby="human-review-title">
    <header className={styles.header}>
      <div>
        <h3 id="human-review-title">Human review</h3>
        {review && <span className={styles.meta}>{review.revision > 0 ? `Saved revision ${review.revision}` : "Not saved"}{dirty ? " · Unsaved edits" : ""}</span>}
      </div>
      {review && <span className={styles.status}>{review.status === "reviewed" ? "Reviewed" : "Draft"}</span>}
    </header>

    {error && <p className={styles.error} role="alert">{error}</p>}
    {notice && <p className={styles.success} role="status">{notice}</p>}
    {loading ? <p className={styles.empty} role="status">Loading review…</p> : !review ? <button type="button" onClick={() => void reload()}>Retry</button> : <div className={styles.body}>
      <div className={styles.reviewProgress}>
        <div className={styles.progressText}><strong>Review progress</strong><span>{reviewedCount} of {hypotheses.length} hypotheses assessed</span></div>
        <div className={styles.progressTrack} role="progressbar" aria-label="Hypotheses assessed" aria-valuemin={0} aria-valuemax={hypotheses.length} aria-valuenow={reviewedCount}>
          <div className={styles.progressFill} style={{ width: `${hypotheses.length ? (reviewedCount / hypotheses.length) * 100 : 0}%` }} />
        </div>
      </div>
      <div className={styles.reviewGuide}>
        <h4>Hypothesis assessments</h4>
        <p>Choose a decision for each hypothesis and add context where useful.</p>
      </div>
      <div className={styles.decisions}>
        {hypotheses.map((title, index) => {
          const choice = review.hypotheses[index];
          if (!choice) return null;
          return <div className={styles.hypothesis} key={index}>
            <div className={styles.hypothesisTop}>
              <span className={styles.hypothesisNumber}>{String(index + 1).padStart(2, "0")}</span>
              <strong>{title}</strong>
              <span className={styles.decisionTag}>{decisions.find((item) => item.value === choice.decision)?.label ?? "Needs review"}</span>
            </div>
            <div className={styles.fieldGrid}>
              <label>Decision
                <select value={choice.decision} disabled={saving} onChange={(event) => change(updateHypothesis(review, index, { decision: event.target.value as HumanReviewDecision }))}>
                  {decisions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
              </label>
              <label>Review note
                <textarea rows={2} maxLength={2000} value={choice.note} disabled={saving} onChange={(event) => change(updateHypothesis(review, index, { note: event.target.value }))} placeholder="Optional" />
              </label>
            </div>
          </div>;
        })}
      </div>
      <div className={styles.reviewGuide}>
        <h4>Incident assessment</h4>
        <p>Capture the impact and remediation context separately from AI-generated findings.</p>
      </div>
      <div className={styles.fieldGrid}>
        <label>Impact notes
          <textarea rows={3} maxLength={4000} value={review.impact_notes} disabled={saving} onChange={(event) => change({ ...review, impact_notes: event.target.value })} placeholder="Optional" />
        </label>
        <label>Remediation notes
          <textarea rows={3} maxLength={4000} value={review.remediation_notes} disabled={saving} onChange={(event) => change({ ...review, remediation_notes: event.target.value })} placeholder="Optional" />
        </label>
      </div>
      <div className={styles.footer}>
        <label>Review status
          <select value={review.status} disabled={saving} onChange={(event) => change({ ...review, status: event.target.value as HumanReview["status"] })}>
            <option value="draft">Draft</option>
            <option value="reviewed" disabled={!canCompleteReview(review.hypotheses)}>Reviewed</option>
          </select>
        </label>
        <div className={styles.actions}>
          <button type="button" className={styles.secondary} disabled={saving} onClick={() => void reload()}>Reload review</button>
          <button type="button" className={styles.primary} disabled={saving || !dirty || (review.status === "reviewed" && !canCompleteReview(review.hypotheses))} onClick={() => void save()}>{saving ? "Saving…" : "Save review"}</button>
        </div>
      </div>
    </div>}
  </section>;
}
