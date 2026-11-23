"""Conservative mechanical metrics. Semantic correctness requires independent review."""

from collections import defaultdict


def _abstained(report: dict) -> bool:
    hypotheses = report.get("hypotheses", [])
    return not hypotheses or all(
        hypothesis.get("status") == "insufficient_evidence" for hypothesis in hypotheses
    )


def _anchor_covered(report: dict, case: dict) -> bool:
    """Exact annotation anchor + cited event overlap; NOT semantic fact precision."""
    required = " ".join(case["gold"]["observed_fact"].lower().split())
    gold_ids = set(case["gold"]["observed_event_ids"])
    return any(
        required in " ".join(fact["statement"].lower().split())
        and bool(gold_ids & set(fact["event_ids"]))
        for fact in report.get("observed_facts", [])
    )


def score_valid_report(report: dict, case: dict) -> dict:
    """Called only AFTER production validate_report has accepted the report."""
    return {
        "citation_membership_pass": True,
        "expected_abstention_match": _abstained(report) == case["gold"]["expected_abstention"],
        "exact_fact_anchor_covered": _anchor_covered(report, case),
        # Human rubric: never hallucinate semantic correctness from lexical heuristics.
        "observed_fact_precision": None,
        "hypothesis_usefulness": None,
    }


def summarize(rows: list[dict], *, mode: str, dataset_sha256: str) -> dict:
    by_profile: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_profile[row["profile"]].append(row)
    summaries = {}
    for profile, group in sorted(by_profile.items()):
        successful = [row for row in group if row["valid"]]
        errors: dict[str, int] = {}
        for row in group:
            if not row["valid"]:
                key = row["error_code"] or "unknown_failure"
                errors[key] = errors.get(key, 0) + 1

        def ratio(field, rows):
            if not rows:
                return None
            return round(sum(bool(row["scores"][field]) for row in rows) / len(rows), 6)

        # Provider usage may be omitted; offline values are not performance measurements.
        token_values = [row["token_usage"] for row in successful if row["token_usage"] is not None]
        summaries[profile] = {
            "attempted": len(group),
            "validated": len(successful),
            "validation_rate": round(len(successful) / len(group), 6) if group else None,
            "citation_membership_rate_on_validated": ratio("citation_membership_pass", successful),
            "abstention_match_rate_on_validated": ratio("expected_abstention_match", successful),
            "exact_fact_anchor_coverage_on_validated": ratio(
                "exact_fact_anchor_covered", successful
            ),
            "observed_fact_precision": None,
            "hypothesis_usefulness": None,
            "mean_prompt_tokens_on_reported_usage": (
                round(sum(d["prompt_tokens"] for d in token_values) / len(token_values), 2)
                if token_values
                else None
            ),
            "mean_completion_tokens_on_reported_usage": (
                round(sum(d["completion_tokens"] for d in token_values) / len(token_values), 2)
                if token_values
                else None
            ),
            "error_codes": errors,
        }
    return {
        "mode": mode,
        "dataset_sha256": dataset_sha256,
        "model_quality_measured": False,  # Structural metrics alone are not model quality.
        "live_structural_metrics_collected": mode == "live",
        "semantic_precision_measured": False,
        "note": (
            "Offline reference adapter validates engineering invariants only; "
            "scores do not measure AI quality."
            if mode == "offline"
            else "Live results measure structural and label-based behavior; "
            "claim precision and usefulness require independent human adjudication."
        ),
        "profiles": summaries,
    }
