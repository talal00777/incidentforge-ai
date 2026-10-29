"""Checks for reproducible chart data and private chart responses."""

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from analytics.charting import CHART_TYPES, chart_caption, chart_series, render_png
from analytics.engine import EventFact, analyze
from incidents.models import Incident
from ingestion.models import IngestionJob, LogEvent, LogSource


def fixture_events():
    start = datetime(2026, 10, 27, 8, tzinfo=UTC)
    return [
        EventFact("a", start, "ERROR", "checkout", "f" * 64),
        EventFact("b", start + timedelta(minutes=5), "INFO", "checkout", "f" * 64),
        EventFact("c", None, "FATAL", "api", "e" * 64),
    ]


def test_chart_series_stable_and_counts_match_input():
    events = fixture_events()
    snapshot = analyze(events)
    assert set(CHART_TYPES) == {"volume", "severity", "fingerprints", "service-errors"}
    volume = chart_series("volume", snapshot, events)
    assert sum(row["total"] for row in volume["rows"]) == 2
    assert sum(row["errors"] for row in volume["rows"]) == 1
    assert chart_series("service-errors", snapshot, events)["rows"] == [
        {"label": "api", "total": 1},
        {"label": "checkout", "total": 1},
    ]
    assert "1 events lack occurrence times" in chart_caption("volume", snapshot, volume)
    assert "2026-10-27T08:00:00Z" in chart_caption("volume", snapshot, volume)
    assert chart_series("fingerprints", snapshot, events)["rows"][0]["label"] == "ffffffffffff"


def test_dense_timeline_is_bounded_and_aggregation_preserves_totals():
    start = datetime(2026, 10, 27, 8, tzinfo=UTC)
    events = [
        EventFact(str(i), start + timedelta(minutes=i), "ERROR", "s", "f") for i in range(1100)
    ]
    snapshot = analyze(events, bucket_minutes=1)
    series = chart_series("volume", snapshot, events)
    assert len(series["rows"]) <= 96
    assert sum(row["total"] for row in series["rows"]) == len(events)
    assert sum(row["errors"] for row in series["rows"]) == len(events)
    assert "per bar" in series["note"]


def test_png_stable_and_figures_closed():
    import matplotlib.pyplot as plt

    events = fixture_events()
    snapshot = analyze(events)
    initial_figures = list(plt.get_fignums())
    for kind in CHART_TYPES:
        first = render_png(kind, snapshot, events)
        assert first[:8] == b"\x89PNG\r\n\x1a\n"
        assert first == render_png(kind, snapshot, events)
    assert plt.get_fignums() == initial_figures


def test_empty_chart_and_invalid_kind():
    snapshot = analyze([])
    assert render_png("volume", snapshot, [])[:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(ValueError):
        chart_series("unsupported", snapshot, [])


@pytest.mark.django_db
def test_charts_restrict_ownership_and_preserve_evidence():
    owner = get_user_model().objects.create_user("chart-owner@example.org", "chart-test-phrase-993")
    outsider = get_user_model().objects.create_user(
        "chart-other@example.org", "chart-test-phrase-994"
    )
    incident = Incident.objects.create(owner=owner, title="Chart privacy")
    job = IngestionJob.objects.create(incident=incident, owner=owner)
    source = LogSource.objects.create(
        incident=incident,
        job=job,
        filename="sample.log",
        object_key="test-chart-object",
        sha256="0" * 64,
        byte_size=1,
    )
    LogEvent.objects.create(
        incident=incident,
        source=source,
        line_start=1,
        line_end=1,
        occurred_at=datetime(2026, 10, 27, 8, tzinfo=UTC),
        observed_at=timezone.now(),
        timestamp_quality="explicit",
        severity="ERROR",
        service="api",
        redacted_message="password=[REDACTED]",
        fingerprint="f" * 64,
    )
    url = f"/api/v1/incidents/{incident.pk}/analysis/charts/severity"
    client = Client()
    assert client.get(url).status_code in (401, 403)
    client.force_login(outsider)
    assert client.get(url).status_code == 404
    client.force_login(owner)
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response["Cache-Control"] == "private, no-store"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert b"password" not in response.content
    assert client.get(url + "?bucket_minutes=2").status_code == 400
    assert client.get(url.replace("severity", "unknown")).status_code == 400
    assert LogEvent.objects.count() == 1
