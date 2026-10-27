from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from incidents.models import Incident
from ingestion.models import LogEvent, LogSource
from ingestion.tasks import process_ingestion


@pytest.mark.django_db
def test_owner_bound_upload_and_idempotent_processing(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner = get_user_model().objects.create_user("ing-owner@example.org", "long-passphrase-unique-83")
        other = get_user_model().objects.create_user("ing-other@example.org", "long-passphrase-unique-84")
        incident = Incident.objects.create(owner=owner, title="Upload integration")
        client = Client()
        client.force_login(other)
        path = f"/api/v1/incidents/{incident.id}/uploads"
        upload = SimpleUploadedFile("service.jsonl", b'{"timestamp":"2026-10-24T10:00:00Z","message":"hello"}\n')
        assert client.post(path, {"files": upload}).status_code == 404
        client.force_login(owner)
        with patch("ingestion.views.process_ingestion.delay"):
            upload = SimpleUploadedFile("service.jsonl", b'{"timestamp":"2026-10-24T10:00:00Z","message":"hello"}\n')
            response = client.post(path, {"files": upload})
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        process_ingestion(job_id)
        process_ingestion(job_id)
        assert LogEvent.objects.filter(incident=incident).count() == 1
        source = LogSource.objects.get(incident=incident)
        assert source.accepted == 1
        client.force_login(other)
        assert client.get(f"/api/v1/incidents/{incident.id}/events").status_code == 404
        assert client.get(f"/api/v1/incidents/{incident.id}/sources").status_code == 404


@pytest.mark.django_db
def test_rejects_binary_content(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner = get_user_model().objects.create_user("binary@example.org", "long-passphrase-unique-85")
        incident = Incident.objects.create(owner=owner, title="Binary rejection")
        client = Client()
        client.force_login(owner)
        response = client.post(f"/api/v1/incidents/{incident.id}/uploads", {"files": SimpleUploadedFile("file.log", b"\x00\x01\x02")})
        assert response.status_code == 400
        assert not LogSource.objects.exists()
