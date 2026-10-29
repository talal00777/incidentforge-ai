"""Bounded, evidence-linked correlation of normalized incident events."""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

VERSION = "m3.3"
MAX_INPUT_EVENTS = 100_000
MAX_GROUPS = 30
MAX_GROUP_EVENTS = 30
MAX_TIMELINE_EVENTS = 60
MAX_TRANSITIONS = 30
IDENTIFIER = re.compile(
    r"(?<![\w-])(?:request[_-]?id|req[_-]?id)\s*[:=]\s*"
    r"([A-Za-z0-9][A-Za-z0-9._:-]{5,95})(?![\w-])",
    re.I,
)
INVALID_IDENTIFIERS = {"[redacted]", "unknown", "none", "null", "undefined"}
ERROR_LEVELS = {"ERROR", "FATAL", "CRITICAL"}


@dataclass(frozen=True)
class CorrelationEvent:
    id: str
    source_id: str
    line_start: int
    line_end: int
    occurred_at: datetime | None
    timestamp_quality: str
    severity: str
    service: str
    trace_id: str
    redacted_message: str


def _instant(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("Occurrence time must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sort_key(event: CorrelationEvent) -> tuple:
    return (
        event.occurred_at is None,
        event.occurred_at or datetime.max.replace(tzinfo=UTC),
        event.source_id,
        event.line_start,
        event.id,
    )


def _clean_id(value: str) -> str | None:
    normalized = value.strip()
    if not (6 <= len(normalized) <= 96):
        return None
    if normalized.lower() in INVALID_IDENTIFIERS or "redacted" in normalized.lower():
        return None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", normalized):
        return None
    return normalized


def _request_id(message: str) -> str | None:
    match = IDENTIFIER.search(message[:4096])
    return _clean_id(match.group(1)) if match else None


def _event_view(event: CorrelationEvent) -> dict:
    return {
        "id": event.id,
        "source_id": event.source_id,
        "line_start": event.line_start,
        "line_end": event.line_end,
        "occurred_at": _instant(event.occurred_at),
        "timestamp_quality": event.timestamp_quality,
        "severity": event.severity.upper()[:16],
        "service": event.service or "",
        "message": event.redacted_message[:360],
    }


def correlate(events: list[CorrelationEvent]) -> dict:
    if len(events) > MAX_INPUT_EVENTS:
        raise ValueError("Correlation event limit exceeded")
    if len({item.id for item in events}) != len(events):
        raise ValueError("Duplicate event identity")
    ordered = sorted(events, key=_sort_key)
    grouped: dict[tuple[str, str], list[CorrelationEvent]] = defaultdict(list)
    for item in ordered:
        trace = _clean_id(item.trace_id)
        if trace:
            grouped[("trace", trace)].append(item)
        request = _request_id(item.redacted_message)
        if request:
            grouped[("request", request)].append(item)

    ranked = sorted(
        ((key, group) for key, group in grouped.items() if len(group) >= 2),
        key=lambda pair: (-len(pair[1]), pair[0][0], pair[0][1]),
    )[:MAX_GROUPS]
    groups = []
    transitions = defaultdict(lambda: {"count": 0, "event_ids": []})
    transition_pairs = set()
    for index, ((kind, identifier), group) in enumerate(ranked, 1):
        key = f"{kind}-{index}"
        timed = [event for event in group if event.occurred_at is not None]
        services = sorted({event.service for event in group if event.service})
        for first, second in zip(timed, timed[1:]):
            if first.service and second.service and first.service != second.service:
                edge = (first.service, second.service)
                pair = (first.id, second.id)
                if pair in transition_pairs:
                    continue
                transition_pairs.add(pair)
                transitions[edge]["count"] += 1
                if len(transitions[edge]["event_ids"]) < 4:
                    transitions[edge]["event_ids"].extend([first.id, second.id])
        groups.append(
            {
                "key": key,
                "kind": kind,
                "event_count": len(group),
                "service_count": len(services),
                "services": services[:12],
                "first_at": _instant(timed[0].occurred_at) if timed else None,
                "last_at": _instant(timed[-1].occurred_at) if timed else None,
                "unknown_time": len(group) - len(timed),
                "truncated": len(group) > MAX_GROUP_EVENTS,
                "events": [_event_view(event) for event in group[:MAX_GROUP_EVENTS]],
            }
        )

    edges = [
        {
            "from_service": src,
            "to_service": dst,
            "count": info["count"],
            "event_ids": list(dict.fromkeys(info["event_ids"]))[:4],
        }
        for (src, dst), info in sorted(
            transitions.items(), key=lambda item: (-item[1]["count"], item[0])
        )[:MAX_TRANSITIONS]
    ]
    timed = [event for event in ordered if event.occurred_at is not None]
    untimed = [event for event in ordered if event.occurred_at is None]
    visible = timed[-MAX_TIMELINE_EVENTS:]
    remaining = MAX_TIMELINE_EVENTS - len(visible)
    if remaining > 0:
        visible += untimed[:remaining]

    return {
        "version": VERSION,
        "total_events": len(events),
        "correlated_groups": len(groups),
        "unknown_time": len(untimed),
        "groups": groups,
        "transitions": edges,
        "timeline": [_event_view(item) for item in visible],
        "timeline_truncated": len(events) > len(visible),
    }
