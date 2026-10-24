"""Versioned public foundation metadata and schema routes."""

from django.conf import settings
from django.test import Client


def test_system_endpoint_contract():
    response = Client().get("/api/v1/system")
    assert response.status_code == 200
    assert response.json() == {
        "name": "IncidentForge AI",
        "api_version": "v1",
        "milestone": "M0",
        "capabilities": ["health", "openapi"],
    }


def test_openapi_schema_is_served():
    response = Client().get("/api/v1/openapi/", HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    assert "api/v1/system" in response.content.decode()


def test_default_permission_requires_authentication():
    assert "rest_framework.permissions.IsAuthenticated" in settings.REST_FRAMEWORK[
        "DEFAULT_PERMISSION_CLASSES"
    ]
