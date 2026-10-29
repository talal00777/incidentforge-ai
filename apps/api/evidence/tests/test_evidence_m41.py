from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from evidence.models import EvidenceSnapshot
from evidence.selection import (
    SelectionFailure,
    build_package,
    validate_citations,
)
from incidents.models import Incident
from ingestion.models import IngestionJob, LogEvent, LogSource


def fixture_events(incident, owner, count=2):
    job = IngestionJob.objects.create(incident=incident, owner=owner)
    source = LogSource.objects.create(
        incident=incident,
        job=job,
        filename="sample.jsonl",
        object_key=str(uuid4()),
        sha256="a" * 64,
        byte_size=200,
        state="complete",
    )
    return [
        LogEvent.objects.create(
            incident=incident,
            source=source,
            line_start=index + 1,
            line_end=index + 1,
            occurred_at=datetime(2026, 10, 27, 8, index, tzinfo=UTC),
            observed_at=timezone.now(),
            timestamp_quality="explicit",
            severity="ERROR",
            service="checkout",
            redacted_message=f"request {index} failed",
            fingerprint="b" * 64,
        )
        for index in range(count)
    ]


@pytest.mark.django_db
def test_preview_requires_owner_and_is_read_only():
    owner = get_user_model().objects.create_user(
        "preview-owner@example.org", "safe-test-password-12"
    )
    outsider = get_user_model().objects.create_user(
        "preview-outsider@example.org", "safe-test-password-13"
    )
    incident = Incident.objects.create(owner=owner, title="Checkout errors")
    event = fixture_events(incident, owner)[0]
    url = f"/api/v1/incidents/{incident.pk}/evidence/preview"
    client = Client()
    body = {"event_ids": [str(event.id)]}
    assert client.post(url, body, content_type="application/json").status_code in (401, 403)
    client.force_login(outsider)
    assert client.post(url, body, content_type="application/json").status_code == 404
    client.force_login(owner)
    response = client.post(url, body, content_type="application/json")
    assert response.status_code == 200
    result = response.json()
    assert result["transmitted"] is False
    assert result["entries"][0]["source_lines"] == [1, 1]
    assert EvidenceSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_consent_snapshot_immutable_endpoints_and_scoping():
    owner = get_user_model().objects.create_user("snap-owner@example.org", "safe-test-password-14")
    outsider = get_user_model().objects.create_user(
        "snap-other@example.org", "safe-test-password-15"
    )
    incident = Incident.objects.create(owner=owner, title="Checkout errors")
    others = Incident.objects.create(owner=outsider, title="Other incident")
    event1, event2 = fixture_events(incident, owner)
    outside_event = fixture_events(others, outsider)[0]
    client = Client()
    client.force_login(owner)
    url = f"/api/v1/incidents/{incident.pk}/evidence/snapshots"
    payload = {"event_ids": [str(event1.pk), str(event2.pk)]}
    response = client.post(url, payload, content_type="application/json")
    assert response.status_code == 400
    payload["expected_sha256"] = build_package(str(incident.pk), [event1, event2])["sha256"]
    payload["privacy_consent"] = {"accepted": False, "policy_version": "1.0"}
    assert client.post(url, payload, content_type="application/json").status_code == 400
    payload["privacy_consent"]["accepted"] = True
    payload["privacy_consent"]["policy_version"] = "0.1"
    assert client.post(url, payload, content_type="application/json").status_code == 400
    payload["privacy_consent"]["policy_version"] = "1.0"
    payload["expected_sha256"] = "0" * 64
    assert client.post(url, payload, content_type="application/json").status_code == 409
    payload["expected_sha256"] = build_package(str(incident.pk), [event1, event2])["sha256"]
    response = client.post(url, payload, content_type="application/json")
    assert response.status_code == 201
    saved = response.json()
    assert saved["event_count"] == 2
    assert saved["transmitted"] is False
    assert client.get(f"{url}/{saved['id']}").status_code == 200
    assert (
        client.patch(f"{url}/{saved['id']}", {}, content_type="application/json").status_code == 405
    )
    assert client.get(url).json()[0]["id"] == saved["id"]
    # The package is independent of request selection order.
    assert (
        build_package(str(incident.id), [event1, event2])["sha256"]
        == build_package(str(incident.id), [event2, event1])["sha256"]
    )
    assert EvidenceSnapshot.objects.count() == 1
    event1.redacted_message = "edited later"
    event1.save(update_fields=["redacted_message"])
    assert client.get(f"{url}/{saved['id']}").json()["entries"][0]["message"] == "request 0 failed"
    payload["event_ids"] = [str(event1.id), str(outside_event.id)]
    assert client.post(url, payload, content_type="application/json").status_code == 400
    client.force_login(outsider)
    assert client.get(f"{url}/{saved['id']}").status_code == 404


@pytest.mark.django_db
def test_privacy_recheck_and_completed_source_required():
    owner = get_user_model().objects.create_user(
        "safety-owner@example.org", "safe-test-password-16"
    )
    incident = Incident.objects.create(owner=owner, title="Review failures")
    event = fixture_events(incident, owner)[0]
    event.redacted_message = "Authorization: Bearer secret123"
    event.save(update_fields=["redacted_message"])
    with pytest.raises(SelectionFailure, match="privacy"):
        build_package(str(incident.id), [event])
    event.redacted_message = "safe redacted failure"
    event.save(update_fields=["redacted_message"])
    event.source.state = "failed"
    event.source.save(update_fields=["state"])
    with pytest.raises(SelectionFailure, match="completed"):
        build_package(str(incident.id), [event])


@pytest.mark.django_db
def test_bounds_duplicates_and_unsupported_citations():
    owner = get_user_model().objects.create_user(
        "bounds-owner@example.org", "safe-test-password-17"
    )
    incident = Incident.objects.create(owner=owner, title="Bounds incident")
    event1, event2 = fixture_events(incident, owner)
    client = Client()
    client.force_login(owner)
    url = f"/api/v1/incidents/{incident.pk}/evidence/preview"
    assert (
        client.post(
            url, {"event_ids": [str(event1.id)] * 2}, content_type="application/json"
        ).status_code
        == 400
    )
    assert (
        client.post(url, {"event_ids": ["invalid"]}, content_type="application/json").status_code
        == 400
    )
    assert (
        client.post(
            url, {"event_ids": [str(event1.id)] * 61}, content_type="application/json"
        ).status_code
        == 400
    )
    package = build_package(str(incident.pk), [event1, event2])
    assert validate_citations(package["entries"], [str(event2.pk)]) == [str(event2.pk)]
    with pytest.raises(SelectionFailure):
        validate_citations(package["entries"], [str(uuid4())])
    with pytest.raises(SelectionFailure):
        validate_citations(package["entries"], [str(event1.pk)] * 2)
    with pytest.raises(SelectionFailure):
        validate_citations(package["entries"], [])
