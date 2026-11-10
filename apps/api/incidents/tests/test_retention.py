from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from evidence.models import EvidenceSnapshot
from incidents.models import Incident, IncidentAuditEvent, ReportPurgeReceipt
from incidents.retention import purge_report_content, retention_cutoff
from incidents.tasks import purge_deleted_evidence, purge_deleted_reports
from ingestion.models import IngestionJob
from investigations.models import (
    InvestigationAttempt,
    InvestigationReport,
    InvestigationReview,
    InvestigationReviewRevision,
    PostmortemVersion,
)


def create_incident(*, deleted_days=None):
    user = get_user_model().objects.create_user(
        f"owner-{uuid4().hex}@example.org", "valid-test-password-527"
    )
    incident = Incident.objects.create(owner=user, title="Gateway timeouts")
    if deleted_days is not None:
        Incident.objects.filter(pk=incident.pk).update(
            deleted_at=timezone.now() - timedelta(days=deleted_days)
        )
        incident.refresh_from_db()
    return user, incident


def create_artifacts(user, incident):
    snapshot = EvidenceSnapshot.objects.create(
        incident=incident,
        created_by=user,
        entries=[],
        sha256="a" * 64,
        item_count=0,
        characters=0,
        payload_bytes=0,
        selection_version="1.0",
        privacy_policy_version="1.0",
        consent_accepted_at=timezone.now(),
    )
    attempt = InvestigationAttempt.objects.create(
        incident=incident,
        snapshot=snapshot,
        created_by=user,
        snapshot_sha256=snapshot.sha256,
        provider="openai",
        model_id="gpt-4o-mini",
        prompt_profile="zero_shot",
        status="succeeded",
        consent_accepted_at=timezone.now(),
    )
    report = InvestigationReport.objects.create(
        attempt=attempt,
        incident=incident,
        snapshot=snapshot,
        created_by=user,
        snapshot_sha256=snapshot.sha256,
        provider="openai",
        model_id="gpt-4o-mini",
        temperature=0.2,
        max_output_tokens=512,
        prompt_profile="zero_shot",
        prompt_version="1.0",
        response_schema_version="1.0",
        report={"incident_summary": "Gateway requests timed out."},
        consent_accepted_at=timezone.now(),
    )
    review = InvestigationReview.objects.create(report=report, created_by=user, latest_revision=1)
    revision = InvestigationReviewRevision.objects.create(
        review=review, number=1, author=user, status="reviewed"
    )
    version = PostmortemVersion.objects.create(
        incident=incident,
        investigation=report,
        review_revision=revision,
        created_by=user,
        version=1,
        content={"schema_version": "1.0"},
        content_sha256="b" * 64,
    )
    return snapshot, attempt, report, review, revision, version


@pytest.mark.django_db
def test_dry_run_preserves_data_and_audit():
    owner, incident = create_incident(deleted_days=100)
    create_artifacts(owner, incident)
    IncidentAuditEvent.objects.create(
        incident=incident, actor=owner, action=IncidentAuditEvent.Action.DELETED
    )
    output = StringIO()
    call_command("purge_deleted_incident_reports", stdout=output)
    assert "eligible=1" in output.getvalue()
    assert "purged=0" in output.getvalue()
    assert "postmortems=1" in output.getvalue()
    assert PostmortemVersion.objects.filter(incident=incident).count() == 1
    assert not ReportPurgeReceipt.objects.filter(incident=incident).exists()
    assert incident.audit_events.count() == 1


@pytest.mark.django_db
def test_purge_deletes_content_in_dependency_order_and_is_idempotent():
    owner, incident = create_incident(deleted_days=120)
    snapshot, attempt, report, review, revision, version = create_artifacts(owner, incident)
    IncidentAuditEvent.objects.create(
        incident=incident, actor=owner, action=IncidentAuditEvent.Action.DELETED
    )
    output = StringIO()
    call_command("purge_deleted_incident_reports", "--execute", stdout=output)
    assert "purged=1" in output.getvalue()
    assert "postmortems=1" in output.getvalue()
    assert not PostmortemVersion.objects.filter(pk=version.pk).exists()
    assert not InvestigationReviewRevision.objects.filter(pk=revision.pk).exists()
    assert not InvestigationReview.objects.filter(pk=review.pk).exists()
    assert not InvestigationReport.objects.filter(pk=report.pk).exists()
    assert not InvestigationAttempt.objects.filter(pk=attempt.pk).exists()
    assert not EvidenceSnapshot.objects.filter(pk=snapshot.pk).exists()
    assert Incident.objects.filter(pk=incident.pk).exists()
    incident.refresh_from_db()
    assert incident.title == "Deleted incident"
    assert incident.description == incident.impact_notes == ""
    assert incident.audit_events.count() == 1
    receipt = ReportPurgeReceipt.objects.get(incident=incident)
    assert receipt.retention_days == 90
    assert receipt.postmortems == receipt.review_revisions == 1
    assert receipt.reports == receipt.attempts == receipt.snapshots == 1
    output = StringIO()
    call_command("purge_deleted_incident_reports", "--execute", stdout=output)
    assert "eligible=0" in output.getvalue()
    assert ReportPurgeReceipt.objects.filter(incident=incident).count() == 1


@pytest.mark.django_db
def test_live_recent_and_active_incidents_are_not_purged():
    old_owner, active = create_incident(deleted_days=100)
    create_artifacts(old_owner, active)
    IngestionJob.objects.create(incident=active, owner=old_owner, state=IngestionJob.State.QUEUED)
    recent_owner, recent = create_incident(deleted_days=3)
    create_artifacts(recent_owner, recent)
    live_owner, live = create_incident()
    create_artifacts(live_owner, live)
    output = StringIO()
    call_command("purge_deleted_incident_reports", "--execute", stdout=output)
    assert "purged=0" in output.getvalue()
    assert ReportPurgeReceipt.objects.count() == 0
    assert PostmortemVersion.objects.count() == 3

    IngestionJob.objects.filter(incident=active).update(state=IngestionJob.State.FAILED)
    output = StringIO()
    call_command("purge_deleted_incident_reports", "--execute", stdout=output)
    assert "purged=1" in output.getvalue()
    assert PostmortemVersion.objects.filter(incident=recent).exists()
    assert PostmortemVersion.objects.filter(incident=live).exists()


@pytest.mark.django_db
def test_purge_rolls_back_if_receipt_cannot_be_saved():
    owner, incident = create_incident(deleted_days=100)
    create_artifacts(owner, incident)
    with patch(
        "incidents.retention.ReportPurgeReceipt.objects.create",
        side_effect=RuntimeError("receipt storage failed"),
    ):
        with pytest.raises(RuntimeError, match="receipt storage failed"):
            purge_report_content(
                incident.pk, cutoff=retention_cutoff(90), retention_days=90, execute=True
            )
    assert PostmortemVersion.objects.filter(incident=incident).count() == 1
    assert EvidenceSnapshot.objects.filter(incident=incident).count() == 1
    incident.refresh_from_db()
    assert incident.title == "Gateway timeouts"
    assert not ReportPurgeReceipt.objects.filter(incident=incident).exists()


@pytest.mark.django_db
def test_bounded_scan_and_cursor():
    incidents = [create_incident(deleted_days=120)[1] for _ in range(3)]
    ids = sorted(str(incident.id) for incident in incidents)
    output = StringIO()
    call_command(
        "purge_deleted_incident_reports",
        "--execute",
        "--max-incidents=1",
        f"--after-incident-id={ids[0]}",
        stdout=output,
    )
    assert "eligible=1" in output.getvalue()
    assert ReportPurgeReceipt.objects.count() == 1
    assert str(ReportPurgeReceipt.objects.first().incident_id) == ids[1]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--minimum-deleted-days=0"], "minimum-deleted-days"),
        (["--max-incidents=0"], "max-incidents"),
        (["--after-incident-id=not-a-uuid"], "after-incident-id"),
    ],
)
@pytest.mark.django_db
def test_invalid_command_options(args, message):
    with pytest.raises(CommandError, match=message):
        call_command("purge_deleted_incident_reports", *args)


def test_scheduled_tasks_require_opt_in():
    with override_settings(RETENTION_CLEANUP_ENABLED=False):
        with patch("incidents.tasks.call_command") as command:
            assert purge_deleted_reports() == "disabled"
            assert purge_deleted_evidence() == "disabled"
            command.assert_not_called()


def test_scheduled_tasks_use_configured_policy():
    with override_settings(
        RETENTION_CLEANUP_ENABLED=True, RETENTION_REPORT_DAYS=150, RETENTION_EVIDENCE_DAYS=45
    ):
        with patch("incidents.tasks.call_command") as command:
            assert purge_deleted_reports() == "complete"
            assert purge_deleted_evidence() == "complete"
    assert command.call_count == 2
    assert command.call_args_list[0].kwargs["minimum_deleted_days"] == 150
    assert command.call_args_list[1].kwargs["minimum_deleted_days"] == 45


@pytest.mark.django_db
def test_evidence_command_uses_configured_default():
    with override_settings(RETENTION_EVIDENCE_DAYS=45):
        create_incident(deleted_days=40)
        output = StringIO()
        call_command("purge_deleted_incident_evidence", stdout=output)
    assert "eligible_incidents=0" in output.getvalue()
