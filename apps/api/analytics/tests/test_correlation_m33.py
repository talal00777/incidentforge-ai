from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from analytics.correlation import CorrelationEvent, correlate


def event(number, *, trace="", message="event", service="checkout", minute=0, timed=True):
    return CorrelationEvent(
        id=f"e-{number}",
        source_id=f"source-{number // 3}",
        line_start=number,
        line_end=number,
        occurred_at=(
            datetime(2026, 10, 27, 8, tzinfo=UTC) + timedelta(minutes=minute) if timed else None
        ),
        timestamp_quality="explicit" if timed else "unknown_timezone",
        severity="ERROR",
        service=service,
        trace_id=trace,
        redacted_message=message,
    )


def test_explicit_trace_and_request_correlation_and_transitions():
    rows = [
        event(1, trace="trace-12345678", message="request_id=req-12345678", service="gateway"),
        event(
            2,
            trace="trace-12345678",
            message="request_id=req-12345678",
            service="checkout",
            minute=1,
        ),
        event(
            3,
            trace="another-123456",
            message="request_id=other-123456",
            service="billing",
            minute=2,
        ),
    ]
    a = correlate(rows)
    assert a == correlate(list(reversed(rows)))
    assert [(g["kind"], g["event_count"]) for g in a["groups"]] == [("request", 2), ("trace", 2)]
    assert a["groups"][0]["events"][0]["line_start"] == 1
    assert a["transitions"] == [
        {
            "from_service": "gateway",
            "to_service": "checkout",
            "count": 1,
            "event_ids": ["e-1", "e-2"],
        }
    ]
    assert all("req-12345678" not in str(g["key"]) for g in a["groups"])


def test_missing_timestamp_explicit_and_not_inferred():
    rows = [event(1, trace="trace-123456", timed=False), event(2, trace="trace-123456", minute=2)]
    result = correlate(rows)
    assert result["unknown_time"] == 1
    assert result["groups"][0]["unknown_time"] == 1
    assert result["groups"][0]["first_at"] == "2026-10-27T08:02:00Z"
    assert result["timeline"][-1]["occurred_at"] is None


def test_bounded_results_and_no_guess_from_unstructured_text():
    rows = [event(i, trace="same-123456", message="possible id 42", minute=i) for i in range(100)]
    result = correlate(rows)
    assert result["groups"][0]["event_count"] == 100
    assert result["groups"][0]["truncated"]
    assert len(result["groups"][0]["events"]) == 30
    assert len(result["timeline"]) == 60
    assert result["timeline_truncated"]
    assert result["groups"][0]["kind"] == "trace"
    assert len(result["transitions"]) == 0


def test_redacted_identifiers_not_correlated():
    rows = [
        event(1, trace="[REDACTED]", message="request_id=[REDACTED]"),
        event(2, trace="[REDACTED]", message="request_id=[REDACTED]"),
    ]
    assert correlate(rows)["groups"] == []


def test_duplicate_event_fails():
    with pytest.raises(ValueError, match="Duplicate"):
        correlate([event(1), event(1)])


@pytest.mark.django_db
def test_relationships_owner_scope_and_evidence_links():
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.utils import timezone

    from incidents.models import Incident
    from ingestion.models import IngestionJob, LogEvent, LogSource

    owner = get_user_model().objects.create_user("correlation-owner@example.org", str(uuid4()))
    outsider = get_user_model().objects.create_user(
        "correlation-outsider@example.org", str(uuid4())
    )
    incident = Incident.objects.create(owner=owner, title="Correlation audit")
    job = IngestionJob.objects.create(incident=incident, owner=owner)
    source = LogSource.objects.create(
        incident=incident,
        job=job,
        filename="synthetic.log",
        object_key=f"test-{uuid4()}",
        sha256="0" * 64,
        byte_size=1,
    )
    for idx, svc in enumerate(("gateway", "checkout"), 1):
        LogEvent.objects.create(
            incident=incident,
            source=source,
            line_start=idx,
            line_end=idx,
            occurred_at=datetime(2026, 10, 27, 8, idx, tzinfo=UTC),
            observed_at=timezone.now(),
            timestamp_quality="explicit",
            severity="ERROR",
            service=svc,
            trace_id="trace-123456",
            redacted_message="failure",
            fingerprint="f" * 64,
        )
    url = f"/api/v1/incidents/{incident.pk}/relationships"
    client = Client()
    assert client.get(url).status_code in (401, 403)
    client.force_login(outsider)
    assert client.get(url).status_code == 404
    client.force_login(owner)
    response = client.get(url)
    assert response.status_code == 200
    result = response.json()
    assert result["correlated_groups"] == 1
    assert result["groups"][0]["event_count"] == 2
    assert result["groups"][0]["events"][0]["source_id"] == str(source.pk)
    assert result["transitions"][0]["count"] == 1
    assert LogEvent.objects.count() == 2
