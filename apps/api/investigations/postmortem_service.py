"""Finalize evidence-linked postmortem versions under an owner-scoped incident lock."""

import hashlib
import json

from django.db import transaction

from incidents.models import Incident
from investigations.models import (
    InvestigationReview,
    InvestigationReviewRevision,
    PostmortemVersion,
)
from investigations.postmortem_content import build_content, content_sha256
from investigations.providers import ProviderFailure
from investigations.validation import validate_report


class PostmortemConflict(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _verified_entries(investigation):
    """Check the original evidence digest without relying on today's privacy-policy version."""
    snapshot = investigation.snapshot
    if (
        snapshot.incident_id != investigation.incident_id
        or snapshot.sha256 != investigation.snapshot_sha256
    ):
        raise PostmortemConflict(
            "source_integrity", "The investigation source could not be verified."
        )
    entries = snapshot.entries
    if not isinstance(entries, list) or len(entries) != snapshot.item_count or not entries:
        raise PostmortemConflict(
            "source_integrity", "The investigation source could not be verified."
        )
    try:
        package = {
            "selection_version": snapshot.selection_version,
            "privacy_policy_version": snapshot.privacy_policy_version,
            "incident_id": str(snapshot.incident_id),
            "events": entries,
        }
        data = json.dumps(
            package, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        if (
            len(data) != snapshot.payload_bytes
            or hashlib.sha256(data).hexdigest() != snapshot.sha256
        ):
            raise ValueError("Evidence mismatch")
        if len({item["event_id"] for item in entries}) != len(entries):
            raise ValueError("Duplicate event")
        validate_report(investigation.report, entries)
    except (KeyError, TypeError, ValueError, ProviderFailure) as exc:
        raise PostmortemConflict(
            "source_integrity", "The investigation source could not be verified."
        ) from exc
    return entries


def verified_content(version):
    """Do not return corrupted content from storage."""
    try:
        valid = (
            version.schema_version == "1.0"
            and content_sha256(version.content) == version.content_sha256
        )
    except (TypeError, ValueError, OverflowError):
        valid = False
    if not valid:
        raise PostmortemConflict(
            "report_integrity", "This report version failed its integrity check."
        )
    return version.content


@transaction.atomic
def create_postmortem(*, incident: Incident, investigation, expected_review_revision: int, actor):
    """Create once per completed review revision; serialize version numbers per incident."""
    locked_incident = Incident.objects.select_for_update().get(pk=incident.pk)
    if locked_incident.deleted_at is not None or investigation.incident_id != locked_incident.id:
        raise PostmortemConflict("incident_unavailable", "The incident is unavailable.")
    try:
        review = InvestigationReview.objects.select_for_update().get(report=investigation)
    except InvestigationReview.DoesNotExist as exc:
        raise PostmortemConflict(
            "review_required", "Complete and save the human review first."
        ) from exc
    if review.latest_revision != expected_review_revision:
        raise PostmortemConflict(
            "review_conflict", "The human review has changed. Reload it before finalizing."
        )
    revision = InvestigationReviewRevision.objects.get(
        review=review, number=expected_review_revision
    )
    count = len(investigation.report.get("hypotheses", []))
    choices = {"reviewed", "accepted_as_working_hypothesis", "rejected"}
    decisions = revision.hypotheses
    complete = (
        revision.status == "reviewed"
        and isinstance(decisions, list)
        and len(decisions) == count
        and all(
            isinstance(item, dict)
            and item.get("index") == index
            and item.get("decision") in choices
            for index, item in enumerate(decisions)
        )
    )
    if not complete:
        raise PostmortemConflict(
            "review_incomplete", "Complete the human review before finalizing."
        )

    existing = PostmortemVersion.objects.filter(
        investigation=investigation, review_revision=revision
    ).first()
    if existing:
        verified_content(existing)
        return existing, False

    evidence_entries = _verified_entries(investigation)
    content = build_content(
        incident=locked_incident,
        investigation=investigation,
        revision=revision,
        evidence_entries=evidence_entries,
    )
    latest = PostmortemVersion.objects.filter(incident=locked_incident).order_by("-version").first()
    saved = PostmortemVersion.objects.create(
        incident=locked_incident,
        investigation=investigation,
        review_revision=revision,
        created_by=actor,
        version=(latest.version + 1) if latest else 1,
        schema_version="1.0",
        content=content,
        content_sha256=content_sha256(content),
    )
    return saved, True
