"""Offline harness and explicitly gated, synthetic-only live prompt comparison."""

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from investigations.evals import EVAL_VERSION
from investigations.evals.dataset import PROFILES, DatasetError, load_cases
from investigations.evals.harness import pending_ledger
from investigations.evals.runner import run_case
from investigations.evals.scoring import summarize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="IncidentForge M6.3 evaluation (offline by default)"
    )
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit evaluated cases (required for live)"
    )
    parser.add_argument("--provider", choices=("groq", "openai", "openrouter"))
    parser.add_argument("--model", help="Server-allowlisted exact model identifier")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--max-live-calls", type=int, default=4)
    parser.add_argument("--confirm-synthetic-transfer", action="store_true")
    parser.add_argument(
        "--output", type=Path, help="Fresh local output directory, defaults outside Git"
    )
    return parser


def _validate_options(args, case_count: int) -> None:
    if args.limit is not None and not 1 <= args.limit <= case_count:
        raise ValueError("--limit must be between 1 and 30")
    if not 0 <= args.temperature <= 1 or not 256 <= args.max_tokens <= 4096:
        raise ValueError("Unsupported evaluation parameter values")
    if args.mode == "live":
        if not (args.confirm_synthetic_transfer and os.getenv("INCIDENTFORGE_EVAL_LIVE") == "1"):
            raise ValueError(
                "Live calls require --confirm-synthetic-transfer and INCIDENTFORGE_EVAL_LIVE=1"
            )
        if not args.provider or not args.model or args.limit is None:
            raise ValueError("Live mode requires --provider, --model and --limit")
        calls_per_case = sum(2 if item == "decomposed_verified" else 1 for item in args.profiles)
        if args.max_live_calls < 1 or args.limit * calls_per_case > args.max_live_calls:
            raise ValueError("Live provider call count exceeds explicit --max-live-calls budget")
    elif args.provider or args.model or args.confirm_synthetic_transfer:
        raise ValueError("Offline mode must not receive provider settings or network consent")


def _default_output() -> Path:
    # cli.py -> evals -> investigations -> api -> apps -> repository -> sibling private.
    repo = Path(__file__).resolve().parents[4]
    return (
        repo.parent
        / "incidentforge-private"
        / "evaluation-results"
        / datetime.now(UTC).strftime("m63-%Y%m%dT%H%M%S%fZ")
    )


def _csv_safe(value: str) -> str:
    """Prevent spreadsheet formula interpretation in independent-review exports."""
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_results(output_dir: Path, rows: list[dict], summary: dict, *, run_meta: dict) -> None:
    # Refuse overwrite to preserve prior audit snapshots and run artifacts.
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "runs.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "summary.json").write_text(
        json.dumps({"run": run_meta, **summary}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "human-review.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "case_id",
                "profile",
                "record_type",
                "record_index",
                "text",
                "evidence_ids",
                "independently_supported_0_or_1",
                "useful_hypothesis_0_or_1",
                "reviewer_notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            if not row["valid"]:
                continue
            report = row["report"]
            for kind, field, text_key, ids_key in (
                ("fact", "observed_facts", "statement", "event_ids"),
                ("hypothesis", "hypotheses", "title", "supporting_event_ids"),
            ):
                for i, item in enumerate(report[field]):
                    writer.writerow(
                        {
                            "case_id": row["case_id"],
                            "profile": row["profile"],
                            "record_type": kind,
                            "record_index": i,
                            "text": _csv_safe(item[text_key]),
                            "evidence_ids": ";".join(item[ids_key]),
                            "independently_supported_0_or_1": "",
                            "useful_hypothesis_0_or_1": "",
                            "reviewer_notes": "",
                        }
                    )
    (output_dir / "harness-status.json").write_text(
        json.dumps(pending_ledger(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "README.txt").write_text(
        "M6.3 outputs are local, with no raw prompts, credentials, or uploaded user evidence.\n"
        "Offline reference-adapter reports are NOT real AI measurements.\n"
        "For live mode, statements and hypotheses require independent review in human-review.csv.\n"
        "Do not claim semantic precision or usefulness before completing the review.\n",
        encoding="utf-8",
    )


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        # Pinned-dataset privacy check is mandatory before any external provider selection.
        cases, digest = load_cases()
        _validate_options(args, len(cases))
        provider = None
        if args.mode == "live":
            from investigations.providers import select_provider

            provider = select_provider(args.provider, args.model)
        selected = cases[: args.limit] if args.limit is not None else cases
        results = [
            run_case(
                case,
                profile,
                mode=args.mode,
                provider=provider,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
            for case in selected
            for profile in args.profiles
        ]
        run_metadata = {
            "eval_version": EVAL_VERSION,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "dataset_sha256": digest,
            "provider": args.provider if args.mode == "live" else None,
            "model": args.model if args.mode == "live" else None,
            "requested_temperature": args.temperature,
            "requested_max_tokens": args.max_tokens,
            "model_effective_parameters_unverified": args.mode == "live",
            "case_count": len(selected),
            "profile_count": len(args.profiles),
        }
        summary = summarize(results, mode=args.mode, dataset_sha256=digest)
        output = args.output if args.output is not None else _default_output()
        write_results(output, results, summary, run_meta=run_metadata)
        print(f"M6.3 mode={args.mode} results={len(results)} output={output}")
        for name, item in summary["profiles"].items():
            print(f"  {name}: {item['validated']}/{item['attempted']} validated")
        return 0 if all(row["valid"] for row in results) else 1
    except (DatasetError, ValueError, OSError) as exc:
        print(f"Evaluation refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        from investigations.providers import ProviderFailure

        if isinstance(exc, ProviderFailure):
            print(f"Evaluation provider unavailable: {exc.code}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
