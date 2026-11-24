from datetime import UTC, datetime, timedelta

import pytest

from analytics.engine import EventFact, analyze


def test_aggregate_known_counts_and_missing_timestamps():
    base = datetime(2026, 10, 27, 8, tzinfo=UTC)
    events = [
        EventFact("a", base, "ERROR", "checkout", "x"),
        EventFact("b", base + timedelta(minutes=1), "INFO", "checkout", "x"),
        EventFact("c", None, "WARN", "api", "y"),
    ]
    result = analyze(events)
    assert (result["total_events"], result["error_events"], result["missing_event_time"]) == (
        3,
        1,
        1,
    )
    assert result["timeline"] == [{"start": "2026-10-27T08:00:00Z", "total": 2, "errors": 1}]
    assert result["service_counts"] == [
        {"service": "checkout", "count": 2, "error_events": 1},
        {"service": "api", "count": 1, "error_events": 0},
    ]
    assert result["anomaly"]["status"] == "insufficient_data"
    assert result["fingerprint_groups"][0]["event_ids"] == ["a", "b"]
    assert result["input_sha256"] == analyze(list(reversed(events)))["input_sha256"]


def test_offset_normalization_and_bucket_boundaries():
    from datetime import timezone

    shifted = datetime(2026, 10, 27, 9, 4, tzinfo=timezone(timedelta(hours=1)))
    result = analyze([EventFact("1", shifted, "ERROR", "api", "")])
    assert result["timeline"][0]["start"] == "2026-10-27T08:00:00Z"


def test_invalid_configuration_and_duplicates():
    item = EventFact("one", None, "INFO", "", "")
    with pytest.raises(ValueError):
        analyze([item, item])
    with pytest.raises(ValueError):
        analyze([item], bucket_minutes=2)


def test_baseline_insufficiency_is_not_anomaly():
    first = datetime(2026, 10, 27, tzinfo=UTC)
    events = [
        EventFact(str(i), first + timedelta(minutes=i * 5), "ERROR", "svc", "x") for i in range(5)
    ]
    assert analyze(events)["anomaly"]["status"] == "insufficient_data"


def test_leave_one_out_anomaly_detects_mid_series_burst():
    first = datetime(2026, 10, 27, 8, tzinfo=UTC)
    events = []
    # Six 5-minute buckets with a spike in bucket index 2 (not only the final bucket).
    bucket_counts = [1, 1, 12, 1, 1, 1]
    counter = 0
    for idx, count in enumerate(bucket_counts):
        for offset in range(count):
            counter += 1
            events.append(
                EventFact(
                    f"evt-{counter}",
                    first + timedelta(minutes=idx * 5, seconds=offset),
                    "ERROR",
                    "checkout",
                    "fp-1",
                )
            )
    result = analyze(events)
    assert result["anomaly"]["status"] == "evaluated"
    assert result["anomaly"]["buckets"] == ["2026-10-27T08:10:00Z"]
