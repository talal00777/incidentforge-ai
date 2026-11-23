"""Strict loader for the pinned synthetic, independently annotated M6.3 dataset."""

import hashlib
import json
import re
from pathlib import Path
from uuid import UUID

from investigations.evals import EVAL_VERSION

CASES_DIR = Path(__file__).resolve().parent / "cases"
CASES_FILE = CASES_DIR / "incidents-v1.jsonl"
MANIFEST_FILE = CASES_DIR / "manifest.json"
CATEGORIES = {
    "clear": 6,
    "multiservice": 6,
    "misleading": 5,
    "insufficient": 5,
    "adversarial": 4,
    "malformed_privacy": 4,
}
PROFILES = ("zero_shot", "few_shot", "decomposed_verified")
MAX_EVENTS = 60
MAX_CHARACTERS = 32000
MAX_PAYLOAD_BYTES = 48000
_CASE_ID = re.compile(r"^IF-EVAL-\d{3}$")


class DatasetError(ValueError):
    """An evaluation fixture is invalid or has failed its integrity check."""


def _canonical(value: object) -> str:
    try:
        result = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DatasetError("An event/source/incident ID is not a UUID") from exc
    if value != result:
        raise DatasetError("Non-canonical UUID in evaluation dataset")
    return result


def _check_case(case: dict) -> None:
    from evidence.selection import _safe_text

    if not isinstance(case, dict) or set(case) != {
        "case_id",
        "category",
        "synthetic",
        "incident_id",
        "entries",
        "gold",
    }:
        raise DatasetError("Unexpected case fields")
    if not isinstance(case["case_id"], str) or not _CASE_ID.fullmatch(case["case_id"]):
        raise DatasetError("Invalid case ID")
    if case["synthetic"] is not True:
        raise DatasetError("Real incident content is prohibited in the bundled corpus")
    _canonical(case["incident_id"])
    entries = case["entries"]
    if not isinstance(entries, list) or not (1 <= len(entries) <= MAX_EVENTS):
        raise DatasetError("Evidence outside case size bounds")
    if sum(len(e.get("message", "")) for e in entries if isinstance(e, dict)) > MAX_CHARACTERS:
        raise DatasetError("Evidence text exceeds privacy policy budget")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "event_id",
            "source_id",
            "source_sha256",
            "source_name",
            "source_lines",
            "occurred_at",
            "timestamp_quality",
            "severity",
            "service",
            "message",
        }:
            raise DatasetError("Invalid evidence schema")
        _canonical(entry["event_id"])
        _canonical(entry["source_id"])
        if entry["event_id"] in seen:
            raise DatasetError("Duplicate evidence identifier")
        seen.add(entry["event_id"])
        if not isinstance(entry["source_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", entry["source_sha256"]
        ):
            raise DatasetError("Invalid source hash")
        for key in ("source_name", "severity", "service", "message"):
            try:
                _safe_text(entry[key])  # Production redaction and control-character gate.
            except Exception as exc:
                # SelectionFailure is not ValueError. Do not disclose fixture text.
                raise DatasetError("Evidence failed the privacy gate") from exc
        lines = entry["source_lines"]
        if not (
            isinstance(lines, list)
            and len(lines) == 2
            and all(type(x) is int and x > 0 for x in lines)
            and lines[0] <= lines[1]
        ):
            raise DatasetError("Invalid source lines")
        if entry["occurred_at"] is None:
            if entry["timestamp_quality"] != "missing":
                raise DatasetError("Missing timestamps must be marked explicitly")
        elif not isinstance(entry["occurred_at"], str) or not entry["occurred_at"].endswith("Z"):
            raise DatasetError("Expected UTC timestamp")
        if entry["timestamp_quality"] not in {"parsed", "missing", "assumed_utc"}:
            raise DatasetError("Invalid timestamp quality")
    gold = case["gold"]
    if not isinstance(gold, dict) or set(gold) != {
        "observed_fact",
        "observed_event_ids",
        "hypothesis",
        "alternative",
        "check",
        "expected_abstention",
        "counterevidence_ids",
        "limitations",
    }:
        raise DatasetError("Invalid annotation schema")
    for key in ("observed_fact", "hypothesis", "alternative", "check"):
        if not isinstance(gold[key], str) or not gold[key].strip():
            raise DatasetError("Missing gold annotation")
    if (
        not isinstance(gold["observed_event_ids"], list)
        or not gold["observed_event_ids"]
        or any(identifier not in seen for identifier in gold["observed_event_ids"])
    ):
        raise DatasetError("Observed facts must point to known evidence")
    if type(gold["expected_abstention"]) is not bool:
        raise DatasetError("Invalid abstention annotation")
    if not isinstance(gold["limitations"], list) or not gold["limitations"]:
        raise DatasetError("Every case must document limitations")
    if (
        not isinstance(gold["counterevidence_ids"], list)
        or not set(gold["counterevidence_ids"]) <= seen
    ):
        raise DatasetError("Counterevidence points outside evidence set")
    if case["category"] not in CATEGORIES:
        raise DatasetError("Unknown incident category")
    # Conservative standalone payload budget; dataset contents are fixed by digest.
    payload = json.dumps(
        {"events": entries, "incident_id": case["incident_id"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise DatasetError("Evidence exceeds payload byte limit")


def load_cases() -> tuple[list[dict], str]:
    """Return pinned dataset and SHA-256; never accept a caller-supplied path."""
    blob = CASES_FILE.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    if set(manifest) != {"version", "sha256", "case_count", "category_counts"}:
        raise DatasetError("Invalid manifest")
    if manifest["version"] != EVAL_VERSION or manifest["sha256"] != digest:
        raise DatasetError("Dataset integrity mismatch; no model calls allowed")
    try:
        cases = [json.loads(line) for line in blob.decode("utf-8").splitlines() if line]
    except (ValueError, UnicodeDecodeError) as exc:
        raise DatasetError("Malformed dataset") from exc
    counts = {name: 0 for name in CATEGORIES}
    ids = set()
    for case in cases:
        _check_case(case)
        if case["case_id"] in ids:
            raise DatasetError("Duplicate case IDs")
        ids.add(case["case_id"])
        counts[case["category"]] += 1
    if len(cases) != 30 or counts != CATEGORIES or manifest["case_count"] != len(cases):
        raise DatasetError("Dataset composition differs from approved evaluation design")
    if manifest["category_counts"] != counts:
        raise DatasetError("Manifest category counts inconsistent")
    return cases, digest
