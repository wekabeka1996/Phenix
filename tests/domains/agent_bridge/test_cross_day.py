from apps.reference.domains.agent_bridge.cross_day import classify_cross_day_session


DAY = 24 * 60 * 60 * 1000


def test_different_utc_date_establishes_cross_day_proof() -> None:
    result = classify_cross_day_session(
        current_first_ts_ms=DAY + 1000,
        current_last_ts_ms=DAY + 2000,
        prior_utc_dates=["1970-01-01"],
        prior_last_ts_ms=DAY - 1000,
    )
    assert result.classification == "different_utc_date"
    assert result.current_utc_date == "1970-01-02"
    assert result.cross_day_proof_established is True


def test_same_date_classification_and_overlap_rejection() -> None:
    result = classify_cross_day_session(
        current_first_ts_ms=6 * 60 * 60 * 1000,
        current_last_ts_ms=6 * 60 * 60 * 1000 + 1000,
        prior_utc_dates=["1970-01-01"],
        prior_last_ts_ms=1000,
    )
    assert result.classification == "same_utc_date_different_hour"
    assert result.cross_day_proof_established is False
    try:
        classify_cross_day_session(
            current_first_ts_ms=1000, current_last_ts_ms=2000,
            prior_utc_dates=["1970-01-01"], prior_last_ts_ms=1500,
        )
    except ValueError as exc:
        assert "overlaps" in str(exc)
    else:
        raise AssertionError("overlapping cross-day evidence was accepted")
