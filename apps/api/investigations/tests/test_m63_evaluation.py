"""M6.3: exercise the real production prompt/validator boundary with a fake adapter."""

import copy
import json
from collections import Counter
from pathlib import Path
from uuid import uuid4

import pytest

from investigations.evals import EVAL_VERSION
from investigations.evals.cli import _csv_safe, _validate_options, build_parser, main
from investigations.evals.dataset import CATEGORIES, DatasetError, _check_case, load_cases
from investigations.evals.harness import pending_ledger
from investigations.evals.runner import reference_report, run_case
from investigations.evals.scoring import score_valid_report, summarize
from investigations.providers import ProviderFailure
from investigations.validation import validate_report


@pytest.fixture(scope="module")
def cases():
    return load_cases()[0]


def test_pinned_corpus_composition_and_safe_input(cases):
    assert len(cases) == 30
    assert Counter(item["category"] for item in cases) == CATEGORIES
    assert all(item["synthetic"] is True for item in cases)
    assert EVAL_VERSION == "M63-001"


@pytest.mark.parametrize("profile", ["zero_shot", "few_shot", "decomposed_verified"])
def test_all_cases_through_production_orchestration_without_network(cases, profile, monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("Offline evaluation unexpectedly attempted a network call")

    monkeypatch.setattr("investigations.providers.urlopen", deny_network)
    for case in cases:
        result = run_case(case, profile, mode="offline")
        assert result["valid"] is True, (case["case_id"], result["error_code"])
        assert result["error_code"] is None
        assert result["latency_ms"] is None
        assert result["token_usage"] is None
        assert result["scores"]["citation_membership_pass"] is True
        assert result["scores"]["expected_abstention_match"] is True
        assert result["scores"]["exact_fact_anchor_covered"] is True
        assert result["scores"]["observed_fact_precision"] is None


def test_unknown_citation_is_rejected_by_real_validator(cases):
    case = cases[0]
    report = reference_report(case)
    report["observed_facts"][0]["event_ids"] = [str(uuid4())]
    with pytest.raises(ProviderFailure) as exc:
        validate_report(report, case["entries"])
    assert exc.value.code == "ungrounded_output"


def test_unsafe_action_is_rejected(cases):
    case = cases[0]
    report = reference_report(case)
    report["suggested_actions"][0]["safety"] = "execute"
    with pytest.raises(ProviderFailure):
        validate_report(report, case["entries"])


def test_cross_case_citation_is_rejected(cases):
    report = reference_report(cases[0])
    report["observed_facts"][0]["event_ids"] = [cases[1]["entries"][0]["event_id"]]
    with pytest.raises(ProviderFailure):
        validate_report(report, cases[0]["entries"])


def test_live_model_parameter_gate(monkeypatch):
    parser = build_parser()
    args = parser.parse_args(
        [
            "--mode",
            "live",
            "--limit",
            "2",
            "--profiles",
            "few_shot",
            "--provider",
            "openai",
            "--model",
            "example-model",
        ]
    )
    with pytest.raises(ValueError, match="synthetic-transfer"):
        _validate_options(args, 30)
    monkeypatch.setenv("INCIDENTFORGE_EVAL_LIVE", "1")
    args.confirm_synthetic_transfer = True
    _validate_options(args, 30)
    args.profiles = ["decomposed_verified", "few_shot"]
    with pytest.raises(ValueError, match="call count"):
        _validate_options(args, 30)


def test_secret_in_dataset_is_blocked_before_inference(cases):
    tampered = copy.deepcopy(cases[0])
    tampered["entries"][0]["message"] = "api_key=not-for-transfer"
    with pytest.raises(DatasetError, match="privacy gate"):
        _check_case(tampered)


def test_dataset_requires_explicit_synthetic_provenance(cases):
    tampered = copy.deepcopy(cases[0])
    tampered["synthetic"] = False
    with pytest.raises(DatasetError):
        _check_case(tampered)


def test_manifest_fails_closed_on_mutated_bytes(tmp_path, monkeypatch):
    from investigations.evals import dataset

    source = dataset.CASES_FILE.read_bytes()
    destination = tmp_path / "cases.jsonl"
    destination.write_bytes(source + b" ")
    monkeypatch.setattr(dataset, "CASES_FILE", destination)
    with pytest.raises(DatasetError, match="integrity"):
        dataset.load_cases()


def test_harness_results_do_not_fabricate_model_quality(cases):
    rows = [run_case(cases[0], "zero_shot", mode="offline")]
    summary = summarize(rows, mode="offline", dataset_sha256=load_cases()[1])
    assert summary["model_quality_measured"] is False
    assert summary["semantic_precision_measured"] is False
    assert summary["profiles"]["zero_shot"]["validation_rate"] == 1.0
    assert summary["profiles"]["zero_shot"]["observed_fact_precision"] is None
    assert score_valid_report(rows[0]["report"], cases[0])["hypothesis_usefulness"] is None


def test_cli_creates_private_style_artifacts_without_provider(tmp_path, monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("Offline CLI contacted a provider")

    monkeypatch.setattr("investigations.providers.urlopen", deny_network)
    target = tmp_path / "evaluation-run"
    assert main(["--mode", "offline", "--limit", "2", "--output", str(target)]) == 0
    assert json.loads((target / "summary.json").read_text())["run"]["case_count"] == 2
    assert len(json.loads((target / "runs.json").read_text())) == 6
    assert (target / "human-review.csv").exists()
    assert (target / "README.txt").exists()
    assert len(json.loads((target / "harness-status.json").read_text())) == 7
    assert main(["--mode", "offline", "--limit", "1", "--output", str(target)]) == 2


def test_no_extra_files_or_untracked_outputs_in_repository():
    from investigations.evals import cli

    destination = cli._default_output()
    assert "incidentforge-private" in destination.parts
    assert "evaluation-results" in destination.parts
    assert not destination.is_relative_to(Path(__file__).resolve().parents[4])


def test_harness_does_not_claim_unverified_release_conditions():
    ledger = pending_ledger()
    assert set(ledger) == {f"HAR-{i:02}" for i in range(1, 8)}
    assert all(item["status"] == "pending_release_evidence" for item in ledger.values())


def test_review_csv_escapes_spreadsheet_formulas():
    assert _csv_safe("=HYPERLINK('unsafe')").startswith("'=")
    assert _csv_safe("@SUM(1,2)").startswith("'@")
    assert _csv_safe("Evidence-backed finding") == "Evidence-backed finding"
