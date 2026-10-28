"""Deterministic, bounded incident event aggregations."""

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median

VERSION = "m3.1"
MAX_EVENTS = 100_000
MAX_GROUPS = 10
BUCKET_MINUTES = 5


@dataclass(frozen=True)
class EventFact:
    id: str
    occurred_at: datetime | None
    severity: str
    service: str
    fingerprint: str


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Event time must be timezone aware")
    return value.astimezone(UTC)


def _bucket(value: datetime, minutes: int) -> datetime:
    current = _utc(value)
    return current.replace(minute=(current.minute // minutes) * minutes, second=0, microsecond=0)


def analyze(events: list[EventFact], *, bucket_minutes: int = BUCKET_MINUTES) -> dict:
    if bucket_minutes not in (1, 5, 15, 60):
        raise ValueError("Unsupported time bucket")
    if len(events) > MAX_EVENTS:
        raise ValueError("Event limit exceeded")
    if len({event.id for event in events}) != len(events):
        raise ValueError("Duplicate event identities")

    severity = Counter()
    service = Counter()
    fingerprints: dict[str, dict] = {}
    buckets: dict[datetime, dict] = defaultdict(lambda: {"total": 0, "errors": 0})
    missing_time = 0
    errors = 0
    for event in events:
        level = event.severity.upper() or "UNKNOWN"
        name = event.service or "unknown"
        is_error = level in {"ERROR", "FATAL", "CRITICAL"}
        severity[level] += 1
        service[name] += 1
        errors += int(is_error)
        if event.fingerprint:
            group = fingerprints.setdefault(
                event.fingerprint, {"fingerprint": event.fingerprint, "count": 0, "event_ids": []}
            )
            group["count"] += 1
            if len(group["event_ids"]) < 5:
                group["event_ids"].append(event.id)
        if event.occurred_at is None:
            missing_time += 1
        else:
            slot = buckets[_bucket(event.occurred_at, bucket_minutes)]
            slot["total"] += 1
            slot["errors"] += int(is_error)

    ordered_slots = sorted(buckets)
    counts = [buckets[t]["total"] for t in ordered_slots]
    anomaly = {
        "status": "insufficient_data",
        "reason": "Requires at least 6 populated time buckets",
        "buckets": [],
    }
    if len(counts) >= 6:
        baseline = counts[:-1]
        center = median(baseline)
        mad = median(abs(n - center) for n in baseline)
        threshold = center + max(3, 6 * 1.4826 * mad)
        outliers = [
            t.isoformat().replace("+00:00", "Z")
            for t in ordered_slots
            if buckets[t]["total"] > threshold
        ]
        anomaly = {
            "status": "evaluated",
            "method": "median_mad",
            "threshold": round(threshold, 3),
            "buckets": outliers,
        }

    result = {
        "algorithm_version": VERSION,
        "bucket_minutes": bucket_minutes,
        "total_events": len(events),
        "error_events": errors,
        "missing_event_time": missing_time,
        "severity_counts": [{"severity": k, "count": v} for k, v in sorted(severity.items())],
        "service_counts": [
            {"service": k, "count": v}
            for k, v in sorted(service.items(), key=lambda x: (-x[1], x[0]))[:MAX_GROUPS]
        ],
        "fingerprint_groups": sorted(
            fingerprints.values(), key=lambda g: (-g["count"], g["fingerprint"])
        )[:MAX_GROUPS],
        "timeline": [
            {
                "start": t.isoformat().replace("+00:00", "Z"),
                "total": buckets[t]["total"],
                "errors": buckets[t]["errors"],
            }
            for t in ordered_slots
        ],
        "anomaly": anomaly,
        "limitations": ["Missing occurrence times excluded from timeline"] if missing_time else [],
    }
    canonical = json.dumps(
        [
            {
                "id": e.id,
                "time": _utc(e.occurred_at).isoformat() if e.occurred_at else None,
                "severity": e.severity,
                "service": e.service,
                "fingerprint": e.fingerprint,
            }
            for e in sorted(events, key=lambda item: item.id)
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    result["input_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result
