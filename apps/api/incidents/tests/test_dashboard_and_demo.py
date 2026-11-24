from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from evidence.models import EvidenceSnapshot
from incidents.models import Incident

User = get_user_model()


def _signed_in_client(email: str) -> tuple[Client, object]:
    user = User.objects.create_user(email=email, password="StrongPassword123!")
    client = Client()
    assert client.login(username=email, password="StrongPassword123!")
    return client, user


@pytest.mark.django_db
def test_dashboard_and_demo_require_authentication():
    client = Client()
    assert client.get("/api/v1/dashboard/summary").status_code in (401, 403)
    assert client.get("/api/v1/demo/scenarios").status_code in (401, 403)
    assert client.post(
        "/api/v1/demo/scenarios",
        {"scenario_id": "checkout-db-pool"},
        content_type="application/json",
    ).status_code in (401, 403)


@pytest.mark.django_db
def test_demo_scenarios_seed_real_multi_service_evidence_and_anomalies():
    client, _ = _signed_in_client("demo-owner@example.com")

    listing = client.get("/api/v1/demo/scenarios")
    assert listing.status_code == 200
    scenario_ids = {item["id"] for item in listing.json()}
    assert scenario_ids == {"checkout-db-pool", "auth-jwt-rotation", "redis-cache-stampede"}

    bad = client.post(
        "/api/v1/demo/scenarios",
        {"scenario_id": "nonexistent"},
        content_type="application/json",
    )
    assert bad.status_code == 400

    for scenario_id in ("checkout-db-pool", "auth-jwt-rotation", "redis-cache-stampede"):
        seeded = client.post(
            "/api/v1/demo/scenarios",
            {"scenario_id": scenario_id},
            content_type="application/json",
        )
        assert seeded.status_code == 201, seeded.content
        payload = seeded.json()
        assert payload["sources_created"] == 3
        assert payload["events_created"] >= 70
        incident = Incident.objects.get(pk=payload["incident"]["id"])
        assert EvidenceSnapshot.objects.filter(
            pk=payload["snapshot_id"], incident=incident
        ).exists()

        # Verify seeded events produce rich real analytics and cross-service correlation via HTTP.
        analysis_resp = client.get(f"/api/v1/incidents/{incident.id}/analysis?bucket_minutes=5")
        assert analysis_resp.status_code == 200
        analysis = analysis_resp.json()
        assert analysis["total_events"] == payload["events_created"]
        assert analysis["error_events"] > 0
        assert len(analysis["service_counts"]) >= 3

        rel_resp = client.get(f"/api/v1/incidents/{incident.id}/relationships")
        assert rel_resp.status_code == 200
        relationships = rel_resp.json()
        assert relationships["correlated_groups"] >= 5
        assert len(relationships["transitions"]) >= 2


@pytest.mark.django_db
def test_dashboard_summary_aggregates_real_metrics_with_strict_owner_isolation():
    client_a, user_a = _signed_in_client("owner-a@example.com")
    client_b, _ = _signed_in_client("owner-b@example.com")

    # Seed one outage for User A and one for User B
    resp_a = client_a.post(
        "/api/v1/demo/scenarios",
        {"scenario_id": "checkout-db-pool"},
        content_type="application/json",
    )
    assert resp_a.status_code == 201
    resp_b = client_b.post(
        "/api/v1/demo/scenarios",
        {"scenario_id": "auth-jwt-rotation"},
        content_type="application/json",
    )
    assert resp_b.status_code == 201

    # Add a resolved incident for User A to verify real MTTR calculation
    resolved = Incident.objects.create(
        owner=user_a,
        title="Resolved DNS resolver timeout",
        service_name="dns-edge",
        severity=Incident.Severity.LOW,
        status=Incident.Status.RESOLVED,
    )
    Incident.objects.filter(pk=resolved.pk).update(
        created_at=timezone.now() - timedelta(minutes=40),
        updated_at=timezone.now() - timedelta(minutes=10),
    )

    summary_resp = client_a.get("/api/v1/dashboard/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()

    assert summary["counts"]["total"] == 2
    assert summary["counts"]["investigating"] == 1
    assert summary["counts"]["resolved"] == 1
    assert summary["counts"]["critical_open"] == 1
    assert summary["telemetry_totals"]["total_sources"] == 3
    assert summary["telemetry_totals"]["total_events"] == resp_a.json()["events_created"]
    assert summary["telemetry_totals"]["total_error_events"] > 0
    assert summary["telemetry_totals"]["total_snapshots"] == 1
    assert summary["mttr_minutes"] is not None
    assert 29.0 <= summary["mttr_minutes"] <= 31.0

    # Strict owner isolation: User B's auth-jwt-rotation title/services must NOT leak to User A
    titles = {item["title"] for item in summary["recent_incidents"]}
    assert resp_b.json()["incident"]["title"] not in titles
    assert len(summary["service_health"]) >= 3
    assert len(summary["recent_activity"]) >= 4
