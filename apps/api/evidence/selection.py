"""Bounded, deterministic, privacy-rechecked evidence package construction."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC
from uuid import UUID

from ingestion.security import CONTROL_CHARACTERS, redact_message

SELECTION_VERSION = "1.0"
PRIVACY_POLICY_VERSION = "1.0"
MAX_EVENTS = 60
MAX_CHARACTERS = 32000
MAX_PAYLOAD_BYTES = 48000


@dataclass
class SelectionFailure(Exception):
    code: str
    message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.message


def canonical_id(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise SelectionFailure("invalid_event_id", "Invalid event identifier.") from exc


def _safe_text(text: str) -> str:
    if not isinstance(text, str) or CONTROL_CHARACTERS.search(text):
        raise SelectionFailure("unsafe_evidence", "Evidence did not pass privacy checks.", 422)
    # Stored redaction is not sufficient authorization to transmit to a model.
    if redact_message(text) != text:
        raise SelectionFailure("unsafe_evidence", "Evidence did not pass privacy checks.", 422)
    return text


def _time(value):
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_package(incident_id: str, events) -> dict:
    """Build a stable, bounded JSON object from already incident-scoped LogEvents."""
    items = []
    for event in events:
        if event.source.incident_id != event.incident_id or str(event.incident_id) != incident_id:
            raise SelectionFailure("invalid_scope", "Evidence does not belong to this incident.")
        if event.source.state != "complete":
            raise SelectionFailure(
                "incomplete_source", "Select events from completed sources only.", 409
            )
        items.append(
            {
                "event_id": str(event.id),
                "source_id": str(event.source_id),
                "source_sha256": event.source.sha256,
                "source_name": _safe_text(event.source.filename),
                "source_lines": [event.line_start, event.line_end],
                "occurred_at": _time(event.occurred_at),
                "timestamp_quality": event.timestamp_quality,
                "severity": _safe_text(event.severity),
                "service": _safe_text(event.service),
                "message": _safe_text(event.redacted_message),
            }
        )
    items.sort(
        key=lambda item: (
            item["occurred_at"] is None,
            item["occurred_at"] or "",
            item["source_id"],
            item["source_lines"][0],
            item["event_id"],
        )
    )
    if not 1 <= len(items) <= MAX_EVENTS:
        raise SelectionFailure("invalid_size", "Select between 1 and 60 events.")
    characters = sum(len(item["message"]) for item in items)
    if characters > MAX_CHARACTERS:
        raise SelectionFailure("over_budget", "Selected evidence exceeds the text budget.", 413)
    package = {
        "selection_version": SELECTION_VERSION,
        "privacy_policy_version": PRIVACY_POLICY_VERSION,
        "incident_id": incident_id,
        "events": items,
    }
    encoded = json.dumps(package, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise SelectionFailure("over_budget", "Selected evidence exceeds the payload budget.", 413)
    return {
        "entries": items,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "event_count": len(items),
        "characters": characters,
        "payload_bytes": len(encoded),
        "privacy_policy_version": PRIVACY_POLICY_VERSION,
        "selection_version": SELECTION_VERSION,
    }


def validate_citations(snapshot_entries: list[dict], cited_event_ids: list[str]) -> list[str]:
    """Fail closed on unknown, duplicate or invalid references; never repair citations."""
    if not isinstance(cited_event_ids, list) or not cited_event_ids:
        raise SelectionFailure("invalid_citation", "At least one evidence citation is required.")
    allowed = {item["event_id"] for item in snapshot_entries}
    checked = [canonical_id(value) for value in cited_event_ids]
    if len(checked) != len(set(checked)) or not set(checked).issubset(allowed):
        raise SelectionFailure(
            "invalid_citation", "Citation does not resolve to selected evidence."
        )
    return checked
