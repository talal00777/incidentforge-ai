"""HTTP liveness/readiness contracts and dependency behavior."""

from unittest.mock import patch

import pytest
from django.test import Client


def test_liveness_is_anonymous_and_dependency_independent():
    response = Client().get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_endpoints_reject_other_methods():
    assert Client().post("/health/live").status_code == 405
    assert Client().post("/health/ready").status_code == 405


@patch("core.views.dependencies_ready", return_value=True)
def test_readiness_healthy(mock_probe):
    response = Client().get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    mock_probe.assert_called_once_with()


@patch("core.views.dependencies_ready", return_value=False)
def test_readiness_unavailable_does_not_leak_infrastructure(mock_probe):
    response = Client().get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "postgres" not in response.content.decode().lower()
    mock_probe.assert_called_once_with()


@pytest.mark.django_db
def test_readiness_real_database_and_broker():
    response = Client().get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@patch("core.health.redis.Redis.from_url")
@patch("core.health.connections")
def test_database_failure_reports_not_ready(mock_connections, mock_redis):
    from core.health import dependencies_ready

    mock_connections.__getitem__.side_effect = OSError("database unavailable")
    mock_redis.return_value.__enter__.return_value.ping.return_value = True
    assert dependencies_ready() is False


@patch("core.health.redis.Redis.from_url")
@patch("core.health.connections")
def test_broker_failure_reports_not_ready(mock_connections, mock_redis):
    from redis.exceptions import ConnectionError

    from core.health import dependencies_ready

    mock_cursor = mock_connections.__getitem__.return_value.cursor.return_value.__enter__
    mock_cursor.return_value.fetchone.return_value = (1,)
    mock_redis.return_value.__enter__.return_value.ping.side_effect = ConnectionError(
        "broker unavailable"
    )
    assert dependencies_ready() is False
