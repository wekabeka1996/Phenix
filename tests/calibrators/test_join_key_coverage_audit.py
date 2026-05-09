from calibrators.datasets.audit_join_key_coverage import (
    _choose_primary_timestamp_field,
    _coerce_timestamp_ms,
    _select_best_pair_key,
)


def test_coerce_timestamp_ms_converts_seconds_and_milliseconds() -> None:
    assert _coerce_timestamp_ms(1773390902.9842906) == 1773390902984
    assert _coerce_timestamp_ms("1778146200000") == 1778146200000
    assert _coerce_timestamp_ms(
        "2026-04-26T20:20:04.606000+00:00") == 1777234804606
    assert _coerce_timestamp_ms(1778146200000) == 1778146200000
    assert _coerce_timestamp_ms("") is None


def test_choose_primary_timestamp_field_prefers_highest_non_null_count() -> None:
    counts = {
        "created_at": 4,
        "ts_ms": 9,
        "event_ts_ms": 2,
    }
    assert _choose_primary_timestamp_field(counts) == "ts_ms"


def test_select_best_pair_key_prefers_canonical_overlap() -> None:
    selected = _select_best_pair_key(
        [
            {
                "key": "symbol",
                "exact_overlap_count": 5,
                "appears_canonical": False,
                "left_non_null_count": 5,
                "right_non_null_count": 7,
            },
            {
                "key": "rid",
                "exact_overlap_count": 2,
                "appears_canonical": True,
                "left_non_null_count": 2,
                "right_non_null_count": 2,
            },
        ]
    )
    assert selected["key"] == "rid"
