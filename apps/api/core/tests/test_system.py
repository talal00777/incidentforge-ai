"""Versioned public foundation metadata and schema routes."""

from django.conf import settings
from django.test import Client


def test_system_endpoint_contract():
    response = Client().get("/api/v1/system")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "IncidentForge AI"
    assert body["api_version"] == "v1"
    assert body["milestone"] == "M6.3"
    assert {
        "health",
        "openapi",
        "auth",
        "incidents",
        "ingestion",
        "analytics",
        "evidence",
        "investigations",
        "reviews",
        "postmortems",
        "evaluations",
    }.issubset(set(body["capabilities"]))


def test_openapi_schema_is_served():
    response = Client().get("/api/v1/openapi/", HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    assert "api/v1/system" in response.content.decode()


def test_default_permission_requires_authentication():
    assert (
        "rest_framework.permissions.IsAuthenticated"
        in settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]
    )
