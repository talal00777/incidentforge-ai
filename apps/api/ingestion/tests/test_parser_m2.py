"""M2.2 parser acceptance and regression cases."""

from datetime import UTC, datetime
from io import BytesIO

import pytest

from ingestion.parser import (
    MAX_LINE_BYTES,
    MAX_RECORD_BYTES,
    VERSION,
    iter_records,
    parse_line,
    parse_timestamp,
)


def parse(data: bytes):
    return list(iter_records(BytesIO(data)))


def accepted(data: bytes):
    return [event for event, warning in parse(data) if warning is None]


def warnings(data: bytes):
    return [warning for event, warning in parse(data) if warning is not None]


def test_unchanged_jsonl_semantics_and_determinism():
    data = (
        b'{"timestamp":"2026-10-25T11:00:00+01:00","level":"ERROR","message":"database timeout"}\n'
        b'{"timestamp":"2026-10-25T11:00:01Z","level":"INFO","message":"retry"}\n'
    )
    first = accepted(data)
    assert len(first) == 2
    assert [(item["line_start"], item["line_end"]) for item in first] == [(1, 1), (2, 2)]
    assert first[0]["occurred_at"] == datetime(2026, 10, 25, 10, tzinfo=UTC)
    assert first[0]["fingerprint"] == accepted(data)[0]["fingerprint"]
    assert all(item["parser_version"] == VERSION for item in first)


def test_multiline_python_and_java_stack_traces_preserve_line_ranges():
    data = (
        b"2026-10-25T10:00:00Z ERROR checkout failed\n"
        b"Traceback (most recent call last):\n"
        b'  File "api.py", line 20, in checkout\n'
        b"ValueError: invalid order\n"
        b"2026-10-25T10:00:01Z WARN next request\n"
        b"    at org.example.Service.execute(Service.java:42)\n"
        b"Caused by: java.sql.SQLException: timeout\n"
    )
    events = accepted(data)
    assert len(events) == 2
    assert (events[0]["line_start"], events[0]["line_end"]) == (1, 4)
    assert "ValueError: invalid order" in events[0]["redacted_message"]
    assert (events[1]["line_start"], events[1]["line_end"]) == (5, 7)
    assert events[1]["severity"] == "WARN"


def test_pretty_and_minified_json_arrays_with_nested_structures():
    data = (
        b'[\n  {"timestamp":"2026-10-25T12:00:00Z", "message":"first", "extra": {"a":[1,2]}},\n'
        b'  {"timestamp":"2026-10-25T12:00:01Z", "message":"comma, bracket ] and escaped \\" quote"}\n]\n'
    )
    events = accepted(data)
    assert len(events) == 2
    assert [(item["line_start"], item["line_end"]) for item in events] == [(2, 2), (3, 3)]
    compact = b'[{"message":"one"},{"message":"two"}]'
    assert [item["redacted_message"] for item in accepted(compact)] == ["one", "two"]


def test_pretty_array_element_spanning_lines_keeps_provenance():
    data = b'[\n {\n  "message": "multiline object",\n  "level": "ERROR"\n },\n {"message":"other"}\n]\n'
    events = accepted(data)
    assert [(item["line_start"], item["line_end"]) for item in events] == [(2, 5), (6, 6)]


def test_json_array_rejects_non_objects_and_records_invalid_json():
    parsed = parse(b'[{"message":"ok"}, 42, {"message": 100}, {broken}]')
    assert sum(warning is None for _, warning in parsed) == 1
    assert [warning for _, warning in parsed if warning] == [
        "invalid_record",
        "invalid_message",
        "invalid_json",
    ]


@pytest.mark.parametrize("data", [b'[{"message":"ok"},]', b'[{"message":"ok"}', b"[] extra"])
def test_invalid_array_structure_is_not_reported_as_success(data):
    assert "invalid_json" in warnings(data)


def test_oversized_array_element_is_rejected_but_next_element_survives():
    data = b'[{"message":"' + b"x" * MAX_RECORD_BYTES + b'"},{"message":"safe"}]'
    assert warnings(data) == ["record_too_long"]
    assert [event["redacted_message"] for event in accepted(data)] == ["safe"]


def test_oversized_physical_line_is_skipped_without_eating_next_line():
    data = b"x" * (MAX_LINE_BYTES + 8) + b"\n2026-10-25T10:00:00Z INFO safe\n"
    parsed = parse(data)
    assert parsed[0] == (None, "line_too_long")
    assert parsed[1][0]["line_start"] == 2


def test_multiline_record_is_bounded_without_leaking_following_stacks():
    data = b"2026-10-25T10:00:00Z ERROR failure\n" + (b"    x\n" * 130)
    data += b"2026-10-25T10:01:00Z INFO recovered\n"
    assert warnings(data) == ["record_too_long"]
    events = accepted(data)
    assert len(events) == 1
    assert events[0]["redacted_message"] == "INFO recovered"
    assert events[0]["line_start"] == 132


def test_timestamp_offsets_are_normalized_without_guessing_dst():
    # Europe/Budapest DST fallback: two local 02:30 times are different UTC instants.
    first, q1 = parse_timestamp("2026-10-25T02:30:00+02:00")
    second, q2 = parse_timestamp("2026-10-25T02:30:00+01:00")
    assert first == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert second == datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    assert q1 == q2 == "explicit"
    assert parse_timestamp("2026-10-25T02:30:00") == (None, "unknown_timezone")
    assert parse_timestamp("not-a-date") == (None, "invalid")
    assert parse_timestamp(None) == (None, "missing")


def test_redaction_covers_all_multiline_lines_and_fingerprint_is_safe():
    data = (
        b"2026-10-25T10:00:00Z ERROR call failed\n"
        b"   Authorization: Bearer ExposedABCD123\n"
        b"   password=AnotherSecret\n"
        b"   contact=alice@example.org\n"
    )
    event = accepted(data)[0]
    assert "ExposedABCD123" not in event["redacted_message"]
    assert "AnotherSecret" not in event["redacted_message"]
    assert "alice@example.org" not in event["redacted_message"]
    assert len(event["fingerprint"]) == 64


def test_invalid_utf8_does_not_contaminate_next_record():
    data = b"\xff\n2026-10-25T10:00:00Z INFO recovered\n"
    assert warnings(data) == ["invalid_utf8"]
    assert len(accepted(data)) == 1


def test_backward_compatible_direct_parse_line():
    event, warning = parse_line(b'{"timestamp":"2026-10-25T12:00:00Z","message":"works"}', 12)
    assert warning is None
    assert (event["line_start"], event["line_end"]) == (12, 12)


def test_large_fixture_has_stable_source_lines():
    record = b'{"timestamp":"2026-10-25T12:00:00Z","message":"fixture"}\n'
    events = accepted(record * 10_000)
    assert len(events) == 10_000
    assert events[0]["line_start"] == 1
    assert events[-1]["line_end"] == 10_000


def test_pretty_standalone_json_document_with_source_line_span():
    data = b'{\n  "timestamp": "2026-10-25T10:00:00Z",\n  "message": "pretty JSON"\n}\n'
    events = accepted(data)
    assert len(events) == 1
    assert (events[0]["line_start"], events[0]["line_end"]) == (1, 4)


def test_excessively_nested_json_is_reported_as_invalid_not_a_worker_crash():
    data = b"{" + (b'"nested":{' * 1100) + b'"message":"hi"' + (b"}" * 1101)
    assert parse(data)[0][1] == "json_too_deep"
