from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from incidents.models import Incident
from ingestion.models import IngestionJob, LogEvent, LogSource
from ingestion.parser import parse_line
from ingestion.storage import store
from ingestion.tasks import _claim_job, _heartbeat, process_ingestion, reconcile_ingestion


def make_job():
    user = get_user_model().objects.create_user(
        "lease-owner@example.org", "long-passphrase-unique-93"
    )
    incident = Incident.objects.create(owner=user, title="Retry-safe processing")
    job = IngestionJob.objects.create(incident=incident, owner=user)
    content = (
        b'{"timestamp":"2026-10-24T10:00:00Z","message":"first"}\n'
        b'{"timestamp":"2026-10-24T10:00:01Z","message":"second"}\n'
    )
    key, digest, size = store(SimpleUploadedFile("service.jsonl", content))
    source = LogSource.objects.create(
        incident=incident,
        job=job,
        filename="service.jsonl",
        object_key=key,
        sha256=digest,
        byte_size=size,
    )
    return job, source


@pytest.mark.django_db(transaction=True)
def test_claim_blocks_duplicate_worker_and_reclaims_expired_lease(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        job, _ = make_job()
        first = _claim_job(job.id)
        assert first is not None
        assert _claim_job(job.id) is None
        IngestionJob.objects.filter(pk=job.pk).update(
            lease_until=timezone.now() - timedelta(seconds=1)
        )
        second = _claim_job(job.id)
        assert second is not None and second != first
        job.refresh_from_db()
        assert job.attempts == 2
        assert job.claim_token == second


@pytest.mark.django_db(transaction=True)
def test_recovery_does_not_duplicate_partially_written_events(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        job, source = make_job()
        token = _claim_job(job.id)
        event, warning = parse_line(b'{"timestamp":"2026-10-24T10:00:00Z","message":"first"}', 1)
        assert warning is None
        _heartbeat(
            job.id,
            token,
            [LogEvent(incident=job.incident, source=source, observed_at=timezone.now(), **event)],
        )
        IngestionJob.objects.filter(pk=job.pk).update(
            lease_until=timezone.now() - timedelta(seconds=1)
        )
        process_ingestion(str(job.id))
        process_ingestion(str(job.id))
        job.refresh_from_db()
        source.refresh_from_db()
        assert job.state == IngestionJob.State.SUCCEEDED
        assert job.accepted == 2
        assert source.accepted == 2
        assert LogEvent.objects.filter(incident=job.incident).count() == 2


@pytest.mark.django_db(transaction=True)
def test_reconciler_dispatches_undelivered_and_expired_jobs(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        job, _ = make_job()
        IngestionJob.objects.filter(pk=job.pk).update(
            requested_at=timezone.now() - timedelta(minutes=2)
        )
        with patch("ingestion.tasks.process_ingestion.delay") as delay:
            assert reconcile_ingestion() >= 1
            delay.assert_any_call(str(job.id))
        token = _claim_job(job.id)
        assert token is not None
        IngestionJob.objects.filter(pk=job.pk).update(
            lease_until=timezone.now() - timedelta(seconds=1)
        )
        with patch("ingestion.tasks.process_ingestion.delay") as delay:
            assert reconcile_ingestion() >= 1
            delay.assert_any_call(str(job.id))


@pytest.mark.django_db(transaction=True)
def test_integrity_failure_terminates_without_disclosing_source_content(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        job, source = make_job()
        LogSource.objects.filter(pk=source.pk).update(sha256="0" * 64)
        process_ingestion(str(job.id))
        job.refresh_from_db()
        assert job.state == IngestionJob.State.FAILED
        assert job.error_code == "INGESTION_SOURCE_INTEGRITY_FAILED"
        assert LogEvent.objects.filter(incident=job.incident).count() == 0


@pytest.mark.django_db(transaction=True)
def test_expired_token_cannot_commit_events(tmp_path):
    from ingestion.tasks import ClaimLost

    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        job, source = make_job()
        token = _claim_job(job.id)
        event, warning = parse_line(b'{"timestamp":"2026-10-24T10:00:00Z","message":"first"}', 1)
        assert warning is None
        IngestionJob.objects.filter(pk=job.pk).update(
            lease_until=timezone.now() - timedelta(seconds=1)
        )
        with pytest.raises(ClaimLost):
            _heartbeat(
                job.id,
                token,
                [
                    LogEvent(
                        incident=job.incident,
                        source=source,
                        observed_at=timezone.now(),
                        **event,
                    )
                ],
            )
        assert LogEvent.objects.filter(source=source).count() == 0


@pytest.mark.django_db(transaction=True)
def test_failed_initial_dispatch_keeps_job_for_reconciliation(tmp_path):
    from django.test import Client

    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner = get_user_model().objects.create_user(
            "dispatch-owner@example.org", "long-passphrase-unique-94"
        )
        incident = Incident.objects.create(owner=owner, title="Broker outage recovery")
        client = Client()
        client.force_login(owner)
        path = f"/api/v1/incidents/{incident.id}/uploads"
        payload = SimpleUploadedFile("dispatch.log", b"2026-10-24T10:00:00Z INFO service ready\n")
        with patch(
            "ingestion.views.process_ingestion.delay", side_effect=RuntimeError("broker down")
        ):
            response = client.post(path, {"files": payload})
        assert response.status_code == 202
        saved = IngestionJob.objects.get(pk=response.json()["job_id"])
        assert saved.state == IngestionJob.State.QUEUED
