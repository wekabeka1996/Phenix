import pytest

from apps.reference.shared.data_primitives.ohlc_validator import (
    GAP_RESET_STATES,
    compute_true_range,
    validate_ohlc,
)


@pytest.mark.parametrize(
    ("open_price", "high_price", "low_price", "close_price", "expected"),
    [
        ("100", "110", "95", "105", (True, None)),
        ("100", "100", "100", "100", (True, None)),
        ("100", "110", "0", "105", (False, "ZERO_LOW")),
        ("100", "110", "-1", "105", (False, "NEGATIVE")),
        ("-1", "110", "95", "105", (False, "NEGATIVE")),
        ("100", "94", "93", "95", (False, "HIGH_BELOW_BODY")),
        ("100", "110", "101", "105", (False, "LOW_ABOVE_BODY")),
        ("100", "94", "95", "96", (False, "INVERTED")),
        (100, 110, 95, 105, (True, None)),
        ("100.5", "110.5", "99.5", "101.5", (True, None)),
        ("100", "105", "95", "95", (True, None)),
        ("100", "105", "100", "105", (True, None)),
    ],
)
def test_validate_ohlc_cases(open_price, high_price, low_price, close_price, expected):
    assert validate_ohlc(open_price, high_price, low_price, close_price) == expected


def test_compute_true_range_first_bar_uses_hl():
    assert str(compute_true_range(high_price="110", low_price="95", prev_close=None)) == "15"


def test_compute_true_range_gap_reset_uses_hl():
    assert "GAP_DETECTED" in GAP_RESET_STATES
    assert str(
        compute_true_range(
            high_price="110",
            low_price="95",
            prev_close="50",
            gap_state="GAP_DETECTED",
        )
    ) == "15"


def test_compute_true_range_uses_prev_close_without_gap():
    assert str(
        compute_true_range(
            high_price="110",
            low_price="95",
            prev_close="80",
            gap_state="CLEAR",
        )
    ) == "30"
