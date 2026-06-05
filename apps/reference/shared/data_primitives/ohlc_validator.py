from __future__ import annotations

import decimal
from typing import Any

GAP_RESET_STATES: frozenset[str] = frozenset({"GAP_DETECTED", "REPAIRED"})

OHLC_INVALID_REASONS: tuple[str, ...] = (
    "ZERO_LOW",
    "NEGATIVE",
    "HIGH_BELOW_BODY",
    "LOW_ABOVE_BODY",
    "INVERTED",
    "INVALID_NUMBER",
)


def _to_decimal(value: Any) -> decimal.Decimal:
    return decimal.Decimal(str(value))


def validate_ohlc(
    open_price: Any,
    high_price: Any,
    low_price: Any,
    close_price: Any,
    *,
    raise_on_invalid: bool = False,
) -> tuple[bool, str | None]:
    try:
        o = _to_decimal(open_price)
        h = _to_decimal(high_price)
        l = _to_decimal(low_price)
        c = _to_decimal(close_price)
    except Exception as exc:
        if raise_on_invalid:
            raise ValueError("INVALID_NUMBER") from exc
        return False, "INVALID_NUMBER"

    if o < 0 or h < 0 or l < 0 or c < 0:
        if raise_on_invalid:
            raise ValueError("NEGATIVE")
        return False, "NEGATIVE"
    if l == 0:
        if raise_on_invalid:
            raise ValueError("ZERO_LOW")
        return False, "ZERO_LOW"
    if h < l:
        if raise_on_invalid:
            raise ValueError("INVERTED")
        return False, "INVERTED"
    if h < max(o, c):
        if raise_on_invalid:
            raise ValueError("HIGH_BELOW_BODY")
        return False, "HIGH_BELOW_BODY"
    if l > min(o, c):
        if raise_on_invalid:
            raise ValueError("LOW_ABOVE_BODY")
        return False, "LOW_ABOVE_BODY"
    return True, None


def compute_true_range(
    *,
    high_price: Any,
    low_price: Any,
    prev_close: Any | None,
    gap_state: str | None = None,
) -> decimal.Decimal:
    high = _to_decimal(high_price)
    low = _to_decimal(low_price)
    if prev_close is None or str(gap_state or "") in GAP_RESET_STATES:
        return high - low
    prev = _to_decimal(prev_close)
    tr_hl = high - low
    tr_hc = abs(high - prev)
    tr_lc = abs(low - prev)
    return max(tr_hl, tr_hc, tr_lc)
