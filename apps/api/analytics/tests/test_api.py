from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from incidents.models import Incident
from ingestion.models import IngestionJob, LogEvent, LogSource


@pytest.mark.django_db
def test_analysis_scoped_and_read_only():
    owner = get_user_model().objects.create_user(
        "analysis-owner@example.org", "analysis-test-password-829"
    )
    outsider = get_user_model().objects.create_user(
        "analysis-other@example.org", "analysis-test-password-830"
    )
    incident = Incident.objects.create(owner=owner, title="Incident analysis")
    job = IngestionJob.objects.create(incident=incident, owner=owner)
    source = LogSource.objects.create(
        incident=incident,
        job=job,
        filename="synthetic.log",
        object_key="synthetic-test-key",
        sha256="0" * 64,
        byte_size=1,
    )
    event = LogEvent.objects.create(
        incident=incident,
        source=source,
        line_start=1,
        line_end=1,
        occurred_at=datetime(2026, 10, 27, tzinfo=UTC),
        observed_at=timezone.now(),
        timestamp_quality="explicit",
        severity="ERROR",
        service="checkout",
        redacted_message="request failed",
        fingerprint="f" * 64,
    )
    url = f"/api/v1/incidents/{incident.pk}/analysis"
    client = Client()
    assert client.get(url).status_code in (401, 403)
    client.force_login(outsider)
    assert client.get(url).status_code == 404
    client.force_login(owner)
    response = client.get(url)
    assert response.status_code == 200
    body = response.json()
    assert body["total_events"] == body["error_events"] == 1
    assert body["fingerprint_groups"][0]["event_ids"] == [str(event.pk)]
    assert client.get(url + "?bucket_minutes=2").status_code == 400
    assert LogEvent.objects.count() == 1
