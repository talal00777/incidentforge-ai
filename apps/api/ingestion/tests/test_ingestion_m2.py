"""Acceptance tests for M2.2's source-linked parser behavior."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from incidents.models import Incident
from ingestion.models import IngestionJob, LogEvent, LogSource
from ingestion.parser import VERSION
from ingestion.tasks import process_ingestion


@pytest.mark.django_db(transaction=True)
def test_json_upload_preserves_array_provenance_diagnostics_and_idempotence(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner = get_user_model().objects.create_user(
            "array-owner@example.org", "test-passphrase-long-166"
        )
        incident = Incident.objects.create(owner=owner, title="JSON arrays")
        client = Client()
        client.force_login(owner)
        contents = (
            b"[\n"
            b' {"timestamp":"2026-10-25T02:30:00+02:00","level":"ERROR","message":"first"},\n'
            b' {"timestamp":"2026-10-25T02:30:00","level":"WARN","message":"second"},\n'
            b' {"timestamp":"incorrect","message":"third"},\n'
            b" 123\n"
            b"]\n"
        )
        with patch("ingestion.views.process_ingestion.delay"):
            response = client.post(
                f"/api/v1/incidents/{incident.id}/uploads",
                {"files": SimpleUploadedFile("example.json", contents)},
            )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        process_ingestion(job_id)
        process_ingestion(job_id)

        events = list(LogEvent.objects.filter(incident=incident).order_by("line_start"))
        source = LogSource.objects.get(incident=incident)
        job = IngestionJob.objects.get(id=job_id)
        assert job.state == IngestionJob.State.SUCCEEDED
        assert source.parser_version == VERSION
        assert source.accepted == 3
        assert source.rejected == 1
        assert [(e.line_start, e.line_end) for e in events] == [(2, 2), (3, 3), (4, 4)]
        assert [e.timestamp_quality for e in events] == ["explicit", "unknown_timezone", "invalid"]
        assert source.warnings == [
            {"code": "invalid_record", "count": 1},
            {"code": "timestamp_invalid", "count": 1},
            {"code": "timestamp_unknown_timezone", "count": 1},
        ]
        assert client.get(f"/api/v1/incidents/{incident.id}/events").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_multiline_log_keeps_one_event_and_redacts_continuation(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner = get_user_model().objects.create_user(
            "stack-owner@example.org", "test-passphrase-long-167"
        )
        incident = Incident.objects.create(owner=owner, title="Stack trace")
        client = Client()
        client.force_login(owner)
        contents = (
            b"2026-10-25T10:00:00Z ERROR failure\n"
            b"Traceback (most recent call last):\n"
            b"   password=super-secret-credential\n"
            b"ValueError: transaction failed\n"
            b"2026-10-25T10:00:01Z INFO recovered\n"
        )
        with patch("ingestion.views.process_ingestion.delay"):
            response = client.post(
                f"/api/v1/incidents/{incident.id}/uploads",
                {"files": SimpleUploadedFile("service.log", contents)},
            )
        assert response.status_code == 202
        process_ingestion(response.json()["job_id"])
        events = list(LogEvent.objects.filter(incident=incident).order_by("line_start"))
        assert len(events) == 2
        assert (events[0].line_start, events[0].line_end) == (1, 4)
        assert "super-secret-credential" not in events[0].redacted_message
        assert events[1].line_start == events[1].line_end == 5


@pytest.mark.django_db(transaction=True)
def test_version_upgrade_replaces_only_incomplete_source_events(tmp_path):
    from django.utils import timezone

    from ingestion.storage import store

    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner = get_user_model().objects.create_user(
            "replay-owner@example.org", "test-passphrase-long-168"
        )
        incident = Incident.objects.create(owner=owner, title="Versioned replay")
        job = IngestionJob.objects.create(incident=incident, owner=owner)
        file_data = b'{"timestamp":"2026-10-25T12:00:00Z","message":"replayed"}\n'
        key, digest, size = store(SimpleUploadedFile("data.jsonl", file_data))
        source = LogSource.objects.create(
            incident=incident,
            job=job,
            filename="data.jsonl",
            object_key=key,
            sha256=digest,
            byte_size=size,
            parser_version="m2.1",
        )
        LogEvent.objects.create(
            incident=incident,
            source=source,
            line_start=1,
            line_end=1,
            occurred_at=None,
            observed_at=timezone.now(),
            timestamp_quality="missing",
            severity="",
            service="",
            trace_id="",
            redacted_message="old partial event",
            fingerprint="0" * 64,
            parser_version="m2.1",
        )
        process_ingestion(str(job.id))
        source.refresh_from_db()
        events = list(LogEvent.objects.filter(source=source))
        assert source.parser_version == VERSION
        assert len(events) == 1
        assert events[0].parser_version == VERSION
        assert events[0].redacted_message == "replayed"
