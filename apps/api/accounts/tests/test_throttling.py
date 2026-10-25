import pytest
from django.test import Client


@pytest.mark.django_db
def test_registration_throttle_limits_repeated_requests():
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    payload = {"email": "rate-limit@example.org", "password": "password"}

    for _ in range(5):
        response = client.post("/api/v1/auth/register", payload, HTTP_X_CSRFTOKEN=token)
        assert response.status_code == 400

    response = client.post("/api/v1/auth/register", payload, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 429
