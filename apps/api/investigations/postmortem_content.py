"""Canonical, frozen postmortem content. This module makes no network calls."""

import hashlib
import json
from copy import deepcopy

SCHEMA_VERSION = "1.0"


def canonical_bytes(content: dict) -> bytes:
    """Serialize report content reproducibly, rejecting non-JSON numeric values."""
    return json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def content_sha256(content: dict) -> str:
    return hashlib.sha256(canonical_bytes(content)).hexdigest()


def build_content(*, incident, investigation, revision, evidence_entries: list[dict]) -> dict:
    """Capture AI and human content independently with source provenance, not raw logs."""
    manifest = [
        {
            "event_id": item["event_id"],
            "source_id": item["source_id"],
            "source_name": item["source_name"],
            "source_sha256": item.get("source_sha256", ""),
            "source_lines": item["source_lines"],
            "occurred_at": item.get("occurred_at"),
            "service": item.get("service", ""),
        }
        for item in evidence_entries
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "incident": {"id": str(incident.id), "title": incident.title},
        "ai": {
            "investigation_id": str(investigation.id),
            "created_at": investigation.created_at.isoformat(),
            "provider": investigation.provider,
            "model_id": investigation.model_id,
            "prompt_profile": investigation.prompt_profile,
            "prompt_version": investigation.prompt_version,
            "response_schema_version": investigation.response_schema_version,
            "generation": {
                "temperature": investigation.temperature,
                "max_output_tokens": investigation.max_output_tokens,
            },
            "usage": {
                "input_tokens": investigation.input_tokens,
                "output_tokens": investigation.output_tokens,
            },
            "consent_accepted_at": investigation.consent_accepted_at.isoformat(),
            "evidence_snapshot": {
                "id": str(investigation.snapshot_id),
                "sha256": investigation.snapshot_sha256,
                "selection_version": investigation.snapshot.selection_version,
                "privacy_policy_version": investigation.snapshot.privacy_policy_version,
            },
            "findings": deepcopy(investigation.report),
        },
        "human": {
            "revision": revision.number,
            "status": revision.status,
            "author_id": str(revision.author_id),
            "reviewed_at": revision.created_at.isoformat(),
            "impact_notes": revision.impact_notes,
            "remediation_notes": revision.remediation_notes,
            "hypotheses": deepcopy(revision.hypotheses),
        },
        "evidence_manifest": manifest,
        "timeline": sorted(
            [
                {
                    "event_id": item["event_id"],
                    "occurred_at": item.get("occurred_at"),
                    "service": item.get("service", ""),
                    "severity": item.get("severity", ""),
                }
                for item in evidence_entries
            ],
            key=lambda event: (event["occurred_at"] is None, event["occurred_at"] or "", event["event_id"]),
        ),
    }
