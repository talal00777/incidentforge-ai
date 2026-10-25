import pytest
from django.contrib.auth import get_user_model
from django.test import Client


@pytest.fixture
def client():
    return Client(enforce_csrf_checks=True)


def csrf(client):
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    assert "csrftoken" in client.cookies
    return response.json()["csrf_token"]


@pytest.mark.django_db
def test_register_login_logout_requires_csrf(client):
    payload = {"email": "Dev@Example.org", "password": "a-safe-unique-passphrase-43"}
    assert client.post("/api/v1/auth/register", payload).status_code == 403
    token = csrf(client)
    response = client.post("/api/v1/auth/register", payload, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 201
    assert response.json()["email"] == "dev@example.org"
    assert "password" not in response.json()
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 403
    refreshed = csrf(client)
    assert client.post("/api/v1/auth/logout", HTTP_X_CSRFTOKEN=refreshed).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 403
    assert client.post("/api/v1/auth/login", payload).status_code == 403
    login_token = csrf(client)
    assert (
        client.post("/api/v1/auth/login", payload, HTTP_X_CSRFTOKEN=login_token).status_code == 200
    )


@pytest.mark.django_db
def test_registration_rejects_weak_password_and_case_insensitive_duplicate(client):
    token = csrf(client)
    payload = {"email": "DEV@example.org", "password": "password"}
    assert client.post("/api/v1/auth/register", payload, HTTP_X_CSRFTOKEN=token).status_code == 400
    get_user_model().objects.create_user("dev@example.org", "a-safe-unique-passphrase-43")
    payload["password"] = "another-unique-passphrase-48"
    assert client.post("/api/v1/auth/register", payload, HTTP_X_CSRFTOKEN=token).status_code == 400


@pytest.mark.django_db
def test_login_denies_wrong_credentials(client):
    token = csrf(client)
    response = client.post(
        "/api/v1/auth/login",
        {"email": "nobody@example.org", "password": "some-password"},
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid credentials"}


@pytest.mark.django_db
def test_password_hashing_and_no_password_in_me():
    user = get_user_model().objects.create_user("hash@example.org", "unique-passphrase-943")
    assert user.password != "unique-passphrase-943"
    assert user.check_password("unique-passphrase-943")
    client = Client()
    client.force_login(user)
    assert "password" not in client.get("/api/v1/auth/me").json()


@pytest.mark.django_db
def test_profile_update_requires_session_and_csrf(client):
    user = get_user_model().objects.create_user("account@example.org", "secure-passphrase-459")
    client.force_login(user)
    endpoint = "/api/v1/auth/me"
    assert (
        client.patch(
            endpoint, data='{"first_name":"Changed"}', content_type="application/json"
        ).status_code
        == 403
    )
    token = csrf(client)
    result = client.patch(
        endpoint,
        data='{"first_name":"Changed","email":"other@example.org"}',
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert result.status_code == 200
    user.refresh_from_db()
    assert user.first_name == "Changed"
    assert user.email == "account@example.org"
