from decimal import Decimal
import pytest

from apps.reference.utils.tp_sl_math import (
    TpslParams,
    TpslConstraints,
    compute_tpsl_levels,
)


def test_long_levels_basic():
    params = TpslParams(
        side="LONG",
        avg_entry_price=Decimal("100"),
        position_qty=Decimal("1"),
        sl_pct=Decimal("0.02"),
        tp_rr=Decimal("2"),
    )
    constraints = TpslConstraints(tick_size=Decimal("0.01"), min_price=Decimal("0.01"))
    levels = compute_tpsl_levels(params, constraints)
    assert levels.sl_price == Decimal("98.00")
    assert levels.tp_price == Decimal("104.00")


def test_short_levels_basic():
    params = TpslParams(
        side="SHORT",
        avg_entry_price=Decimal("50"),
        position_qty=Decimal("1"),
        sl_pct=Decimal("0.05"),
        tp_rr=Decimal("1.5"),
    )
    constraints = TpslConstraints(tick_size=Decimal("0.01"), min_price=Decimal("0.01"))
    levels = compute_tpsl_levels(params, constraints)
    assert levels.sl_price == Decimal("52.50")
    assert levels.tp_price == Decimal("46.25")


def test_rounding_and_min_price():
    params = TpslParams(
        side="LONG",
        avg_entry_price=Decimal("1.001"),
        position_qty=Decimal("1"),
        sl_pct=Decimal("0.5"),  # 50%
        tp_rr=Decimal("1"),
    )
    constraints = TpslConstraints(tick_size=Decimal("0.01"), min_price=Decimal("0.10"))
    levels = compute_tpsl_levels(params, constraints)
    # raw sl = 0.5005 -> rounded down to 0.50, but min_price=0.10 so stays 0.50
    assert levels.sl_price == Decimal("0.50")
    # raw tp = 1.5015 -> 1.50 after rounding
    assert levels.tp_price == Decimal("1.50")


def test_invalid_params_raise():
    params = TpslParams(
        side="LONG",
        avg_entry_price=Decimal("100"),
        position_qty=Decimal("1"),
        sl_pct=Decimal("0"),
        tp_rr=Decimal("1"),
    )
    constraints = TpslConstraints(tick_size=Decimal("0.01"), min_price=Decimal("0.01"))
    with pytest.raises(ValueError):
        compute_tpsl_levels(params, constraints)
