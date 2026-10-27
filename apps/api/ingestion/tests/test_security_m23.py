"""M2.3 evidence boundary and owner-scoping regression tests."""

from io import BytesIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from incidents.models import Incident
from ingestion.models import IngestionJob, LogSource
from ingestion.parser import iter_records
from ingestion.security import UploadRejected, redact_message, validate_upload


def upload(name, content):
    return SimpleUploadedFile(name, content)


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("logs.zip", b"safe text", "unsupported_file_type"),
        ("logs.log", b"PK\x03\x04fake archive", "binary_file"),
        ("logs.log", b"\x1f\x8bcompressed", "binary_file"),
        ("logs.log", b"%PDF-1.7\ntext", "binary_file"),
        ("logs.txt", b"valid\x00but\x00binary", "binary_file"),
        ("logs.txt", b"red \xff invalid", "invalid_utf8"),
        ("logs.log", b"terminal\x1b[31m color", "binary_file"),
        ("logs.json", b"not actually json", "invalid_json_type"),
        ("logs.jsonl", b"[{}]", "invalid_jsonl_type"),
        ("empty.log", b"", "invalid_file_size"),
    ],
)
def test_rejects_disguised_and_invalid_evidence(name, content, code):
    with override_settings(INGESTION_MAX_FILE_BYTES=1024):
        candidate = upload(name, content)
        with pytest.raises(UploadRejected) as error:
            validate_upload(candidate)
        assert error.value.code == code
        assert candidate.tell() == 0


def test_streaming_size_validation_resets_cursor():
    with override_settings(INGESTION_MAX_FILE_BYTES=8):
        candidate = upload("service.log", b"123456789")
        with pytest.raises(UploadRejected, match="size limit"):
            validate_upload(candidate)
        assert candidate.tell() == 0


def test_valid_unicode_json_array_and_safe_display_basename():
    with override_settings(INGESTION_MAX_FILE_BYTES=2048):
        candidate = upload("C:\\temp\\trace.json", b'\xef\xbb\xbf[{"message":"caf\xc3\xa9"}]')
        assert validate_upload(candidate) == "trace.json"
        assert candidate.read().startswith(b"\xef\xbb\xbf")


def test_redaction_masks_structured_credentials_and_emails():
    message = (
        '"api_key":"example-secret" password=VerySecret '
        "Authorization: Bearer bearer-secret\n"
        "Cookie: session=foo; sessionid=bar\n"
        "postgres://alice:pwd123@database:5432/db\n"
        "contact=alice@example.com"
    )
    sanitized = redact_message(message)
    for secret in (
        "example-secret",
        "VerySecret",
        "bearer-secret",
        "session=foo",
        "pwd123",
        "alice@example.com",
    ):
        assert secret not in sanitized
    assert sanitized.count("[REDACTED]") >= 4
    assert "[REDACTED_EMAIL]" in sanitized


def test_parser_redacts_structured_metadata_and_message():
    records = list(
        iter_records(
            BytesIO(
                b'{"timestamp":"2026-10-27T10:00:00Z",'
                b'"message":"api_key=abc123",'
                b'"service":"Authorization: Bearer leakedservice",'
                b'"trace_id":"token=leakedtrace"}\n'
            )
        )
    )
    event, warning = records[0]
    assert warning is None
    assert "abc123" not in event["redacted_message"]
    assert "leakedservice" not in event["service"]
    assert "leakedtrace" not in event["trace_id"]


@pytest.mark.django_db
def test_authenticated_owner_only_can_access_nested_ingestion_endpoints(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        User = get_user_model()
        owner = User.objects.create_user("m23-owner@example.org", "valid-passphrase-201")
        stranger = User.objects.create_user("m23-stranger@example.org", "valid-passphrase-202")
        incident = Incident.objects.create(owner=owner, title="Private evidence")
        job = IngestionJob.objects.create(incident=incident, owner=owner)
        client = Client()
        base = f"/api/v1/incidents/{incident.id}"
        client.force_login(stranger)
        assert client.get(f"{base}/sources").status_code == 404
        assert client.get(f"{base}/events").status_code == 404
        assert client.get(f"{base}/jobs/{job.id}").status_code == 404
        assert (
            client.post(
                f"{base}/uploads", {"files": upload("sample.log", b"INFO safe\n")}
            ).status_code
            == 404
        )
        assert not LogSource.objects.exists()


@pytest.mark.django_db
def test_rejected_upload_has_no_job_or_storage_side_effects(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner = get_user_model().objects.create_user(
            "m23-binary@example.org", "valid-passphrase-203"
        )
        incident = Incident.objects.create(owner=owner, title="Reject before storage")
        client = Client()
        client.force_login(owner)
        url = f"/api/v1/incidents/{incident.id}/uploads"
        response = client.post(url, {"files": upload("secret.log", b"PK\x03\x04archive")})
        assert response.status_code == 400
        assert response.json()["code"] == "binary_file"
        assert not IngestionJob.objects.exists()
        assert not LogSource.objects.exists()
        assert not list(tmp_path.iterdir())


@pytest.mark.django_db
def test_valid_upload_still_returns_accepted_and_sanitizes_filename(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner = get_user_model().objects.create_user(
            "m23-valid@example.org", "valid-passphrase-204"
        )
        incident = Incident.objects.create(owner=owner, title="Accepted evidence")
        client = Client()
        client.force_login(owner)
        with patch("ingestion.views.process_ingestion.delay"):
            response = client.post(
                f"/api/v1/incidents/{incident.id}/uploads",
                {"files": upload("trace.jsonl", b'{"message":"safe"}\n')},
            )
        assert response.status_code == 202
        assert LogSource.objects.get().filename == "trace.jsonl"
