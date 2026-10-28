"""Storage retention and historical normalized-evidence redaction regressions."""

import hashlib
from datetime import timedelta
from io import StringIO
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from incidents.models import Incident, IncidentAuditEvent
from ingestion.models import IngestionJob, LogEvent, LogSource
from ingestion.storage import path_for, store


def evidence(owner, incident, state=IngestionJob.State.SUCCEEDED):
    job = IngestionJob.objects.create(incident=incident, owner=owner, state=state)
    key, sha, size = store(SimpleUploadedFile("legacy.log", b"INFO existing source\n"))
    source = LogSource.objects.create(
        incident=incident,
        job=job,
        filename="api_key=older-secret.log",
        object_key=key,
        sha256=sha,
        byte_size=size,
        state=LogSource.State.COMPLETE,
    )
    message = "Authorization: Bearer sensitive-token"
    event = LogEvent.objects.create(
        incident=incident,
        source=source,
        line_start=1,
        line_end=1,
        observed_at=timezone.now(),
        timestamp_quality="explicit",
        severity="ERROR",
        service="password=service-secret",
        trace_id="token=trace-secret",
        redacted_message=message,
        fingerprint=hashlib.sha256(("ERROR:" + message).encode()).hexdigest(),
    )
    return job, source, event


def owner_and_incident(*, deleted_days=None):
    owner = get_user_model().objects.create_user(
        f"retention-{uuid4().hex}@example.org", "long-valid-passphrase-208"
    )
    incident = Incident.objects.create(owner=owner, title="Governed evidence")
    if deleted_days is not None:
        incident.deleted_at = timezone.now() - timedelta(days=deleted_days)
        incident.save(update_fields=["deleted_at"])
    return owner, incident


@pytest.mark.django_db
def test_historical_redaction_is_explicit_idempotent_and_does_not_modify_raw(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner, incident = owner_and_incident()
        _, source, event = evidence(owner, incident)
        original_raw = path_for(source.object_key).read_bytes()
        output = StringIO()
        call_command("redact_stored_evidence", "--incident-id", str(incident.id), stdout=output)
        assert "changed_events=1" in output.getvalue()
        event.refresh_from_db()
        source.refresh_from_db()
        assert "sensitive-token" in event.redacted_message
        assert "older-secret" in source.filename

        output = StringIO()
        call_command(
            "redact_stored_evidence", "--execute", "--incident-id", str(incident.id),
            stdout=output,
        )
        assert "changed_events=1" in output.getvalue()
        event.refresh_from_db()
        source.refresh_from_db()
        for secret in ("sensitive-token", "service-secret", "trace-secret"):
            assert secret not in (event.redacted_message + event.service + event.trace_id)
        assert "older-secret" not in source.filename
        assert event.fingerprint == hashlib.sha256(
            ("ERROR:" + event.redacted_message).encode()
        ).hexdigest()
        assert path_for(source.object_key).read_bytes() == original_raw

        output = StringIO()
        call_command("redact_stored_evidence", "--execute", stdout=output)
        assert "changed_events=0" in output.getvalue()
        assert "changed_sources=0" in output.getvalue()


@pytest.mark.django_db
def test_historical_redaction_skips_active_ingestion(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner, incident = owner_and_incident()
        _, _, event = evidence(owner, incident, IngestionJob.State.RUNNING)
        output = StringIO()
        call_command("redact_stored_evidence", "--execute", stdout=output)
        event.refresh_from_db()
        assert "sensitive-token" in event.redacted_message
        assert "skipped_active=2" in output.getvalue()


@pytest.mark.django_db
def test_retention_dry_run_then_purge_preserves_tombstone_and_audit(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner, old = owner_and_incident(deleted_days=45)
        _, source, event = evidence(owner, old)
        IncidentAuditEvent.objects.create(
            incident=old, actor=owner, action=IncidentAuditEvent.Action.DELETED,
        )
        raw = path_for(source.object_key)
        output = StringIO()
        call_command("purge_deleted_incident_evidence", stdout=output)
        assert "eligible_incidents=1" in output.getvalue()
        assert "executed=False" in output.getvalue()
        assert raw.exists() and LogEvent.objects.filter(pk=event.pk).exists()

        output = StringIO()
        call_command("purge_deleted_incident_evidence", "--execute", stdout=output)
        assert "deleted_events=1" in output.getvalue()
        assert "deleted_sources=1" in output.getvalue()
        assert "deleted_files=1" in output.getvalue()
        assert not raw.exists()
        assert not LogEvent.objects.filter(pk=event.pk).exists()
        assert Incident.objects.filter(pk=old.pk).exists()
        assert IncidentAuditEvent.objects.filter(incident=old).count() == 1


@pytest.mark.django_db
def test_retention_skips_active_jobs_recent_deletions_and_live_incidents(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner, active = owner_and_incident(deleted_days=40)
        _, active_source, _ = evidence(owner, active, IngestionJob.State.QUEUED)
        owner2, recent = owner_and_incident(deleted_days=2)
        _, recent_source, _ = evidence(owner2, recent)
        owner3, live = owner_and_incident()
        _, live_source, _ = evidence(owner3, live)
        output = StringIO()
        call_command("purge_deleted_incident_evidence", "--execute", stdout=output)
        assert "skipped_active=1" in output.getvalue()
        for source in (active_source, recent_source, live_source):
            assert LogSource.objects.filter(pk=source.pk).exists()
            assert path_for(source.object_key).exists()


@pytest.mark.django_db
def test_retention_rejects_untrusted_object_key_before_mutation(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner, incident = owner_and_incident(deleted_days=40)
        _, source, event = evidence(owner, incident)
        source.object_key = "../../outside"
        source.save(update_fields=["object_key"])
        with pytest.raises(CommandError, match="invalid object key"):
            call_command("purge_deleted_incident_evidence", "--execute")
        assert LogSource.objects.filter(pk=source.pk).exists()
        assert LogEvent.objects.filter(pk=event.pk).exists()


@pytest.mark.django_db
def test_retention_missing_raw_object_is_safe(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner, incident = owner_and_incident(deleted_days=45)
        _, source, _ = evidence(owner, incident)
        path_for(source.object_key).unlink()
        output = StringIO()
        call_command("purge_deleted_incident_evidence", "--execute", stdout=output)
        assert "missing_files=1" in output.getvalue()
        assert not LogSource.objects.filter(pk=source.pk).exists()


@pytest.mark.django_db
def test_retention_refuses_symlink_object(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner, incident = owner_and_incident(deleted_days=45)
        _, source, event = evidence(owner, incident)
        path_for(source.object_key).unlink()
        outside = tmp_path.parent / f"retention-outside-{uuid4().hex}.txt"
        outside.write_text("private outside data")
        try:
            path_for(source.object_key).symlink_to(outside)
        except (OSError, NotImplementedError):
            outside.unlink()
            pytest.skip("Symlinks unavailable")
        try:
            with pytest.raises(CommandError, match="not a regular file"):
                call_command("purge_deleted_incident_evidence", "--execute")
            assert outside.read_text() == "private outside data"
            assert LogEvent.objects.filter(pk=event.pk).exists()
        finally:
            path_for(source.object_key).unlink()
            outside.unlink()

@pytest.mark.django_db
def test_historical_redaction_supports_bounded_cursor_scans(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner, incident = owner_and_incident()
        _, source1, event1 = evidence(owner, incident)
        _, source2, event2 = evidence(owner, incident)
        output = StringIO()
        call_command(
            "redact_stored_evidence", "--execute", "--max-events", "1",
            "--max-sources", "1", "--incident-id", str(incident.id), stdout=output,
        )
        assert "scanned_events=1" in output.getvalue()
        assert "scanned_sources=1" in output.getvalue()
        assert "sensitive-token" not in output.getvalue()

        output = StringIO()
        call_command(
            "redact_stored_evidence", "--execute", "--max-events", "1",
            "--max-sources", "1", "--incident-id", str(incident.id),
            "--after-event-id", str(min(event1.pk, event2.pk)),
            "--after-source-id", str(min(source1.pk, source2.pk)),
            stdout=output,
        )
        assert "scanned_events=1" in output.getvalue()
        assert "scanned_sources=1" in output.getvalue()
        for event in (event1, event2):
            event.refresh_from_db()
            assert "sensitive-token" not in event.redacted_message
        for source in (source1, source2):
            source.refresh_from_db()
            assert "older-secret" not in source.filename
