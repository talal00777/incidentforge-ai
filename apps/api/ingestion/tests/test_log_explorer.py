import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from incidents.models import Incident
from ingestion.models import IngestionJob, LogEvent, LogSource

User = get_user_model()


def _setup_incident_logs(email: str):
    user = User.objects.create_user(email=email)
    client = Client()
    client.force_login(user)

    incident = Incident.objects.create(
        owner=user,
        title="Checkout pool saturation",
        service_name="checkout-api",
        severity=Incident.Severity.CRITICAL,
        status=Incident.Status.INVESTIGATING,
    )
    job = IngestionJob.objects.create(
        incident=incident, owner=user, state=IngestionJob.State.SUCCEEDED
    )
    src_a = LogSource.objects.create(
        incident=incident,
        job=job,
        filename="checkout-api.log",
        object_key=f"test/{incident.id}/a",
        sha256="a" * 64,
        byte_size=1024,
        state=LogSource.State.COMPLETE,
    )
    src_b = LogSource.objects.create(
        incident=incident,
        job=job,
        filename="postgres-primary.log",
        object_key=f"test/{incident.id}/b",
        sha256="b" * 64,
        byte_size=512,
        state=LogSource.State.COMPLETE,
    )
    now = timezone.now()
    events_a = []
    for idx in range(1, 16):
        sev = "ERROR" if idx in (7, 8, 9) else ("WARN" if idx == 6 else "INFO")
        msg = (
            f"PoolTimeout waiting for db slot attempt={idx} code=503"
            if sev == "ERROR"
            else f"Processed checkout request step={idx}"
        )
        events_a.append(
            LogEvent.objects.create(
                incident=incident,
                source=src_a,
                line_start=idx,
                line_end=idx,
                occurred_at=now,
                observed_at=now,
                timestamp_quality="explicit",
                severity=sev,
                service="checkout-api",
                trace_id="trace-checkout-99" if idx in (6, 7, 8) else "",
                redacted_message=msg,
                fingerprint="fp-pool-timeout" if sev == "ERROR" else f"fp-info-{idx}",
            )
        )
    # Event in a different source sharing the same trace_id
    LogEvent.objects.create(
        incident=incident,
        source=src_b,
        line_start=1,
        line_end=1,
        occurred_at=now,
        observed_at=now,
        timestamp_quality="explicit",
        severity="ERROR",
        service="postgres-primary",
        trace_id="trace-checkout-99",
        redacted_message="FATAL: remaining connection slots are reserved",
        fingerprint="fp-pg-slots",
    )
    return client, user, incident, events_a


@pytest.mark.django_db
def test_log_explorer_filters_regex_trace_and_fingerprint():
    client, _, incident, _ = _setup_incident_logs("explorer@example.com")

    # Trace filter
    by_trace = client.get(f"/api/v1/incidents/{incident.id}/events?trace_id=trace-checkout-99")
    assert by_trace.status_code == 200
    assert by_trace.json()["count"] == 4
    assert all(row["trace_id"] == "trace-checkout-99" for row in by_trace.json()["results"])

    # Fingerprint filter
    by_fp = client.get(f"/api/v1/incidents/{incident.id}/events?fingerprint=fp-pool-timeout")
    assert by_fp.status_code == 200
    assert by_fp.json()["count"] == 3

    # Valid regex search
    by_rx = client.get(
        f"/api/v1/incidents/{incident.id}/events?search=PoolTimeout.*code=503&regex=true"
    )
    assert by_rx.status_code == 200
    assert by_rx.json()["count"] == 3

    # Invalid regex rejected cleanly with 400
    bad_rx = client.get(f"/api/v1/incidents/{incident.id}/events?search=[unclosed&regex=true")
    assert bad_rx.status_code == 400

    # Nested quantifier ReDoS pattern rejected cleanly with 400
    redos_rx = client.get(
        f"/api/v1/incidents/{incident.id}/events",
        {"search": "(a+)+b", "regex": "true"},
    )
    assert redos_rx.status_code == 400


@pytest.mark.django_db
def test_log_explorer_facets_and_context_drawer():
    client, _, incident, events_a = _setup_incident_logs("facets@example.com")
    other_user = User.objects.create_user(email="intruder@example.com")
    other_client = Client()
    other_client.force_login(other_user)

    # Facets endpoint
    facets_resp = client.get(f"/api/v1/incidents/{incident.id}/events/facets")
    assert facets_resp.status_code == 200
    facets = facets_resp.json()
    assert facets["total_events"] == 16
    sev_map = {item["value"]: item["count"] for item in facets["severities"]}
    assert sev_map["ERROR"] == 4
    assert sev_map["WARN"] == 1
    svc_map = {item["value"]: item["count"] for item in facets["services"]}
    assert svc_map["checkout-api"] == 15
    assert svc_map["postgres-primary"] == 1
    assert facets["top_fingerprints"][0]["fingerprint"] == "fp-pool-timeout"
    assert facets["top_fingerprints"][0]["count"] == 3

    # Context drawer endpoint on line 8 with window=4 -> lines 4..7 before, lines 9..12 after
    target = events_a[7]  # line_start=8
    ctx_resp = client.get(f"/api/v1/incidents/{incident.id}/events/{target.id}/context?window=4")
    assert ctx_resp.status_code == 200
    ctx = ctx_resp.json()
    assert ctx["event"]["line_start"] == 8
    assert ctx["event"]["source_filename"] == "checkout-api.log"
    assert [row["line_start"] for row in ctx["before"]] == [4, 5, 6, 7]
    assert [row["line_start"] for row in ctx["after"]] == [9, 10, 11, 12]
    assert ctx["related_trace_count"] == 4
    assert ctx["same_fingerprint_count"] == 3

    # Owner isolation on facets and context
    assert other_client.get(f"/api/v1/incidents/{incident.id}/events/facets").status_code == 404
    assert (
        other_client.get(f"/api/v1/incidents/{incident.id}/events/{target.id}/context").status_code
        == 404
    )
