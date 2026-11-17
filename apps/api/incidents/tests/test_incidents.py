import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from incidents.models import Incident, IncidentAuditEvent


@pytest.fixture
def users(db):
    model = get_user_model()
    return (
        model.objects.create_user("owner@example.org", "passphrase-111"),
        model.objects.create_user("other@example.org", "passphrase-222"),
    )


@pytest.fixture
def owner_client(users):
    client = Client(enforce_csrf_checks=True)
    client.force_login(users[0])
    token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    return client, token


@pytest.mark.django_db
def test_owner_can_create_list_filter_update_archive_and_delete(owner_client, users):
    client, token = owner_client
    data = {
        "title": "Checkout latency regression",
        "service_name": "checkout-api",
        "timezone": "Europe/Budapest",
        "severity": "high",
    }
    response = client.post("/api/v1/incidents", data, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 201
    incident_id = response.json()["id"]
    incident = Incident.objects.get(pk=incident_id)
    assert incident.owner == users[0]
    assert incident.audit_events.filter(action="created").count() == 1
    listing = client.get("/api/v1/incidents").json()
    assert listing["count"] == 1
    assert listing["results"][0]["id"] == incident_id
    assert client.get("/api/v1/incidents?status=resolved").json()["count"] == 0
    assert client.get("/api/v1/incidents?status=bad").status_code == 400
    response = client.patch(
        f"/api/v1/incidents/{incident_id}",
        data={"status": "archived", "impact_notes": "Intermittent failures"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    assert incident.audit_events.filter(action="updated").count() == 1
    assert (
        client.delete(f"/api/v1/incidents/{incident_id}", HTTP_X_CSRFTOKEN=token).status_code == 204
    )
    incident.refresh_from_db()
    assert incident.deleted_at is not None
    assert client.get(f"/api/v1/incidents/{incident_id}").status_code == 404
    assert client.get("/api/v1/incidents").json()["count"] == 0
    assert incident.audit_events.filter(action="deleted").exists()


@pytest.mark.django_db
def test_cross_owner_reads_and_mutations_are_not_found(users, owner_client):
    owner, other = users
    incident = Incident.objects.create(owner=other, title="Private incident")
    client, token = owner_client
    assert client.get("/api/v1/incidents").json()["count"] == 0
    assert client.get(f"/api/v1/incidents/{incident.id}").status_code == 404
    assert (
        client.patch(
            f"/api/v1/incidents/{incident.id}",
            {"title": "tampered"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/incidents/{incident.id}", HTTP_X_CSRFTOKEN=token).status_code == 404
    )
    incident.refresh_from_db()
    assert incident.title == "Private incident"
    assert incident.deleted_at is None
    assert not IncidentAuditEvent.objects.filter(incident=incident).exists()


@pytest.mark.django_db
def test_unauthenticated_requests_and_input_validation(users, owner_client):
    guest = Client()
    assert guest.get("/api/v1/incidents").status_code == 403
    assert guest.post("/api/v1/incidents", {"title": "Unauthenticated"}).status_code == 403
    client, token = owner_client
    assert (
        client.post("/api/v1/incidents", {"title": "ab"}, HTTP_X_CSRFTOKEN=token).status_code == 400
    )
    assert (
        client.post(
            "/api/v1/incidents",
            {"title": "Valid title", "timezone": "Nowhere/Unknown"},
            HTTP_X_CSRFTOKEN=token,
        ).status_code
        == 400
    )
    assert client.post("/api/v1/incidents", {"title": "Valid title"}).status_code == 403


@pytest.mark.django_db
def test_owner_field_cannot_be_overridden(owner_client, users):
    client, token = owner_client
    result = client.post(
        "/api/v1/incidents",
        {"title": "Safe incident", "owner": str(users[1].pk)},
        HTTP_X_CSRFTOKEN=token,
    )
    assert result.status_code == 201
    assert Incident.objects.get(pk=result.json()["id"]).owner == users[0]


@pytest.mark.django_db
def test_incident_search_is_owner_scoped_and_bounded(owner_client, users):
    client, _ = owner_client
    owner, other = users
    matches_title = Incident.objects.create(owner=owner, title="Payment gateway slowdown")
    matches_service = Incident.objects.create(
        owner=owner, title="Queue lag", service_name="gateway-worker"
    )
    Incident.objects.create(owner=owner, title="Unrelated change")
    Incident.objects.create(owner=other, title="Gateway internal outage")
    results = client.get("/api/v1/incidents?search=GATEWAY").json()
    assert results["count"] == 2
    assert {item["id"] for item in results["results"]} == {
        str(matches_title.id),
        str(matches_service.id),
    }
    assert client.get("/api/v1/incidents?search=%20gateway%20").json()["count"] == 2
    assert client.get("/api/v1/incidents?search=" + "z" * 101).status_code == 400
    assert client.get("/api/v1/incidents?status=resolved&search=gateway").json()["count"] == 0
