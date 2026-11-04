"""Authoritative validation of snapshot integrity and model evidence claims."""

import hashlib
import json
from uuid import UUID

from evidence.selection import (
    MAX_CHARACTERS,
    MAX_EVENTS,
    MAX_PAYLOAD_BYTES,
    PRIVACY_POLICY_VERSION,
    SelectionFailure,
    _safe_text,
    validate_citations,
)
from investigations.providers import ProviderFailure

MAX_TEXT = 850


def snapshot_entries(snapshot) -> list[dict]:
    entries = snapshot.entries
    if not isinstance(entries, list) or not (1 <= len(entries) <= MAX_EVENTS):
        raise ProviderFailure(
            "snapshot_integrity", "The evidence snapshot failed integrity checks.", 409
        )
    try:
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError("Bad evidence item")
            UUID(str(item["event_id"]))
            UUID(str(item["source_id"]))
            for key in ("message", "source_name", "severity", "service"):
                _safe_text(item[key])
        if len({item["event_id"] for item in entries}) != len(entries):
            raise ValueError("Duplicate evidence IDs")
        if sum(len(item["message"]) for item in entries) > MAX_CHARACTERS:
            raise ValueError("Evidence too large")
        if snapshot.privacy_policy_version != PRIVACY_POLICY_VERSION:
            raise ValueError("Privacy policy changed")
        package = {
            "selection_version": snapshot.selection_version,
            "privacy_policy_version": snapshot.privacy_policy_version,
            "incident_id": str(snapshot.incident_id),
            "events": entries,
        }
        payload = json.dumps(
            package, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        if len(payload) > MAX_PAYLOAD_BYTES or len(payload) != snapshot.payload_bytes:
            raise ValueError("Evidence byte budget mismatch")
        if hashlib.sha256(payload).hexdigest() != snapshot.sha256:
            raise ValueError("Evidence hash mismatch")
        if len(entries) != snapshot.item_count:
            raise ValueError("Evidence count mismatch")
    except (KeyError, TypeError, ValueError, SelectionFailure) as exc:
        raise ProviderFailure(
            "snapshot_integrity", "The evidence snapshot failed integrity checks.", 409
        ) from exc
    return entries


def _validate_text(value, *, allow_empty=False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > MAX_TEXT
        or (not value.strip() and not allow_empty)
    ):
        raise ProviderFailure("ungrounded_output", "The AI result failed evidence validation.", 422)
    try:
        return _safe_text(value)
    except SelectionFailure as exc:
        raise ProviderFailure(
            "ungrounded_output", "The AI result failed privacy validation.", 422
        ) from exc


def _strings(items, limit):
    if not isinstance(items, list) or len(items) > limit:
        raise ProviderFailure(
            "ungrounded_output", "The AI result failed structural validation.", 422
        )
    for item in items:
        _validate_text(item)


def _references(items, entries, *, required):
    if not isinstance(items, list) or len(items) > MAX_EVENTS or (required and not items):
        raise ProviderFailure(
            "ungrounded_output", "The AI result has invalid evidence references.", 422
        )
    if not items:
        return
    try:
        checked = validate_citations(entries, items)
        if checked != items:
            raise SelectionFailure(
                "invalid_citation", "Non-canonical evidence IDs are not supported."
            )
    except SelectionFailure as exc:
        raise ProviderFailure(
            "ungrounded_output", "The AI result contains unsupported evidence references.", 422
        ) from exc


def validate_facts(data: dict, entries: list[dict]) -> dict:
    if not isinstance(data, dict) or set(data) != {"observed_facts", "limitations"}:
        raise ProviderFailure(
            "invalid_response", "The AI result failed structural validation.", 422
        )
    facts = data["observed_facts"]
    if not isinstance(facts, list) or len(facts) > 12:
        raise ProviderFailure(
            "invalid_response", "The AI result failed structural validation.", 422
        )
    for item in facts:
        if not isinstance(item, dict) or set(item) != {"statement", "event_ids"}:
            raise ProviderFailure(
                "invalid_response", "The AI result failed structural validation.", 422
            )
        _validate_text(item["statement"])
        _references(item["event_ids"], entries, required=True)
    _strings(data["limitations"], 10)
    return data


def validate_report(data: dict, entries: list[dict]) -> dict:
    if (
        not isinstance(data, dict)
        or set(data)
        != {
            "schema_version",
            "incident_summary",
            "observed_facts",
            "hypotheses",
            "suggested_actions",
            "limitations",
        }
        or data["schema_version"] != "1.0"
    ):
        raise ProviderFailure(
            "invalid_response", "The AI result failed structural validation.", 422
        )
    _validate_text(data["incident_summary"])
    validate_facts(
        {"observed_facts": data["observed_facts"], "limitations": data["limitations"]}, entries
    )
    hypotheses = data["hypotheses"]
    if not isinstance(hypotheses, list) or len(hypotheses) > 6:
        raise ProviderFailure(
            "invalid_response", "The AI result failed structural validation.", 422
        )
    for item in hypotheses:
        required = {
            "title",
            "status",
            "supporting_event_ids",
            "contradicting_event_ids",
            "alternative_explanations",
            "further_checks",
        }
        if not isinstance(item, dict) or set(item) != required:
            raise ProviderFailure(
                "invalid_response", "The AI result failed structural validation.", 422
            )
        if item["status"] not in {
            "supported_but_not_proven",
            "plausible_unconfirmed",
            "contradicted",
            "insufficient_evidence",
        }:
            raise ProviderFailure(
                "invalid_response", "The AI result has an unsupported status.", 422
            )
        _validate_text(item["title"])
        _references(
            item["supporting_event_ids"],
            entries,
            required=item["status"] not in {"insufficient_evidence", "contradicted"},
        )
        _references(item["contradicting_event_ids"], entries, required=False)
        if set(item["supporting_event_ids"]) & set(item["contradicting_event_ids"]):
            raise ProviderFailure(
                "ungrounded_output", "Conflicting evidence citations were reported.", 422
            )
        _strings(item["alternative_explanations"], 6)
        _strings(item["further_checks"], 8)
    actions = data["suggested_actions"]
    if not isinstance(actions, list) or len(actions) > 8:
        raise ProviderFailure(
            "invalid_response", "The AI result failed structural validation.", 422
        )
    for item in actions:
        if (
            not isinstance(item, dict)
            or set(item) != {"action", "safety", "rationale_event_ids"}
            or item["safety"] != "review_only"
        ):
            raise ProviderFailure(
                "invalid_response", "The AI result failed safety validation.", 422
            )
        _validate_text(item["action"])
        _references(item["rationale_event_ids"], entries, required=True)
    return data
