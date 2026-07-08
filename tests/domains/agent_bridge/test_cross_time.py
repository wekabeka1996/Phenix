from apps.reference.domains.agent_bridge.cross_time import (
    TimeWindowEvidence,
    classify_time_windows,
    cross_time_proof_established,
)


HOUR = 60 * 60 * 1000
DAY = 24 * HOUR


def test_classifies_archived_close_gap_and_same_day_different_hour() -> None:
    windows = classify_time_windows([
        TimeWindowEvidence(window_id="prior", first_ts_ms=10 * HOUR, last_ts_ms=10 * HOUR + 1000, packet_count=100, archived=True),
        TimeWindowEvidence(window_id="later", first_ts_ms=15 * HOUR, last_ts_ms=15 * HOUR + 1000, packet_count=100, archived=True),
        TimeWindowEvidence(window_id="current", first_ts_ms=16 * HOUR, last_ts_ms=16 * HOUR + 1000, packet_count=100),
    ])
    assert [item.temporal_class for item in windows] == [
        "archived_prior_window", "same_day_different_hour", "same_runtime_close_gap"
    ]
    assert cross_time_proof_established(windows) is True


def test_classifies_different_day_and_rejects_overlap() -> None:
    windows = classify_time_windows([
        TimeWindowEvidence(window_id="day1", first_ts_ms=DAY - HOUR, last_ts_ms=DAY - 1, packet_count=100),
        TimeWindowEvidence(window_id="day2", first_ts_ms=DAY + HOUR, last_ts_ms=DAY + HOUR + 1000, packet_count=100),
    ])
    assert windows[1].temporal_class == "different_day"
    try:
        classify_time_windows([
            TimeWindowEvidence(window_id="one", first_ts_ms=1000, last_ts_ms=3000, packet_count=1),
            TimeWindowEvidence(window_id="two", first_ts_ms=2000, last_ts_ms=4000, packet_count=1),
        ])
    except ValueError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("overlapping windows were accepted")
