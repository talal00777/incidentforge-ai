import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from incidents.models import Incident

User = get_user_model()


def _client_for(email: str):
    user = User.objects.create_user(email=email, password="StrongPassword123!")
    client = Client()
    assert client.login(username=email, password="StrongPassword123!")
    return client, user


@pytest.mark.django_db
def test_war_room_timeline_and_action_items_lifecycle():
    client, user = _client_for("warroom-owner@example.com")
    other_client, _ = _client_for("warroom-other@example.com")

    seeded = client.post(
        "/api/v1/demo/scenarios",
        {"scenario_id": "checkout-db-pool"},
        content_type="application/json",
    )
    assert seeded.status_code == 201
    incident_id = seeded.json()["incident"]["id"]

    # Unified timeline contains seeded operator entries, audit, sources, and snapshot
    tl_resp = client.get(f"/api/v1/incidents/{incident_id}/timeline")
    assert tl_resp.status_code == 200
    tl_items = tl_resp.json()
    kinds = {row["source_kind"] for row in tl_items}
    assert {"operator", "audit", "source", "snapshot"}.issubset(kinds)

    # Create a new operator mitigation entry
    created = client.post(
        f"/api/v1/incidents/{incident_id}/timeline",
        {
            "entry_type": "mitigation",
            "body": "Rolled back v2.41.3 and drained stalled connections.",
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]
    assert created.json()["deletable"] is True
    assert created.json()["actor_label"] == user.email

    # Delete operator entry
    deleted = client.delete(f"/api/v1/incidents/{incident_id}/timeline/{entry_id}")
    assert deleted.status_code == 204

    # Action items seeded + CRUD + completed_at auto-management
    items_resp = client.get(f"/api/v1/incidents/{incident_id}/action-items")
    assert items_resp.status_code == 200
    assert len(items_resp.json()) == 3

    add_resp = client.post(
        f"/api/v1/incidents/{incident_id}/action-items",
        {
            "title": "Enforce 2s statement_timeout in PgBouncer",
            "priority": "p0",
            "owner_label": "@db-oncall",
        },
        content_type="application/json",
    )
    assert add_resp.status_code == 201
    item_id = add_resp.json()["id"]
    assert add_resp.json()["completed_at"] is None

    done_resp = client.patch(
        f"/api/v1/incidents/{incident_id}/action-items/{item_id}",
        {"status": "done"},
        content_type="application/json",
    )
    assert done_resp.status_code == 200
    assert done_resp.json()["status"] == "done"
    assert done_resp.json()["completed_at"] is not None

    reopen_resp = client.patch(
        f"/api/v1/incidents/{incident_id}/action-items/{item_id}",
        {"status": "open"},
        content_type="application/json",
    )
    assert reopen_resp.status_code == 200
    assert reopen_resp.json()["completed_at"] is None

    assert (
        client.delete(f"/api/v1/incidents/{incident_id}/action-items/{item_id}").status_code == 204
    )

    # Cross-owner isolation
    assert other_client.get(f"/api/v1/incidents/{incident_id}/timeline").status_code == 404
    assert other_client.get(f"/api/v1/incidents/{incident_id}/action-items").status_code == 404
    assert Incident.objects.filter(pk=incident_id).exists()
