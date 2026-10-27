from ingestion.parser import parse_line, parse_timestamp, redact


def test_explicit_timestamp_and_redaction():
    event, warning = parse_line(
        b'{"timestamp":"2026-10-24T10:00:00Z","level":"error","message":"password=private@example.org"}',
        1,
    )
    assert warning is None
    assert event["timestamp_quality"] == "explicit"
    assert event["occurred_at"].tzinfo is not None
    assert "private@example.org" not in event["redacted_message"]


def test_unknown_timezone_is_never_assumed():
    assert parse_timestamp("2026-10-24T10:00:00")[1] == "unknown_timezone"


def test_bad_encoding_and_json_reported():
    assert parse_line(b"\xff", 1)[1] == "invalid_utf8"
    assert parse_line(b'{"message":', 2)[1] == "invalid_json"


def test_redaction_strips_bearer_token():
    assert "ABCDSecret" not in redact("Authorization: Bearer ABCDSecret")
