"""Pure serialization checks that run without a database or AI provider."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from investigations.postmortem_content import build_content, canonical_bytes, content_sha256


def test_canonical_hash_is_deterministic_and_sensitive_to_content():
    first = {"b": [2, 3], "a": {"name": "incident"}}
    reordered = {"a": {"name": "incident"}, "b": [2, 3]}
    assert canonical_bytes(first) == canonical_bytes(reordered)
    assert content_sha256(first) == content_sha256(reordered)
    changed = deepcopy(first)
    changed["a"]["name"] = "different"
    assert content_sha256(changed) != content_sha256(first)


def test_report_capture_copies_source_and_omits_raw_log_messages():
    now = datetime(2026, 11, 7, tzinfo=UTC)
    snapshot = SimpleNamespace(selection_version="1.0", privacy_policy_version="1.0")
    original = {"incident_summary": "Provider failed", "hypotheses": []}
    investigation = SimpleNamespace(
        id=uuid4(), snapshot_id=uuid4(), snapshot_sha256="a" * 64,
        created_at=now, consent_accepted_at=now,
        provider="openai", model_id="gpt-4o-mini", prompt_profile="few_shot",
        prompt_version="1.0", response_schema_version="1.0", temperature=0.2,
        max_output_tokens=2048, input_tokens=20, output_tokens=42,
        snapshot=snapshot, report=original,
    )
    revision = SimpleNamespace(
        number=2, author_id=uuid4(), created_at=now, status="reviewed",
        impact_notes="Several checkouts failed", remediation_notes="Review retries",
        hypotheses=[],
    )
    entries = [
        {
            "event_id": str(uuid4()), "source_id": str(uuid4()),
            "source_sha256": "b" * 64, "source_name": "gateway.log",
            "source_lines": [1, 3], "occurred_at": "2026-11-07T00:30:00Z",
            "service": "gateway", "severity": "ERROR", "message": "Sensitive log text",
        }
    ]
    content = build_content(
        incident=SimpleNamespace(id=uuid4(), title="Payment incident"),
        investigation=investigation, revision=revision, evidence_entries=entries,
    )
    original["incident_summary"] = "Modified"
    assert content["ai"]["findings"]["incident_summary"] == "Provider failed"
    assert content["timeline"][0]["service"] == "gateway"
    assert "Sensitive log text" not in json.dumps(content)
    assert len(content_sha256(content)) == 64
