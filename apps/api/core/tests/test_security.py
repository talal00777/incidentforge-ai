"""Foundation-level HTTP isolation and response metadata."""

import json
import re

from django.test import Client

from core.logging import JsonFormatter

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def test_request_id_is_generated_by_server():
    response = Client().get("/api/v1/system", HTTP_X_REQUEST_ID="untrusted-client-value")
    correlation_id = response["X-Request-ID"]
    assert correlation_id != "untrusted-client-value"
    assert UUID_RE.fullmatch(correlation_id)


def test_request_id_is_unique_per_request():
    client = Client()
    first = client.get("/health/live")["X-Request-ID"]
    second = client.get("/health/live")["X-Request-ID"]
    assert first != second


def test_json_formatter_does_not_include_custom_secret_fields():
    import logging

    record = logging.LogRecord(
        name="incidentforge",
        level=logging.INFO,
        pathname="",
        lineno=1,
        msg="health probe",
        args=(),
        exc_info=None,
    )
    record.api_key = "should-never-be-logged"
    result = json.loads(JsonFormatter().format(record))
    assert result["message"] == "health probe"
    assert "api_key" not in result
    assert "should-never-be-logged" not in json.dumps(result)
