from decimal import Decimal

import pytest

from vfoundation.apps.reference.domains.execution_position.bracket_aggregator import (
    AggregatedBracketLevels,
    AggregatedOcoError,
    AggregatedOcoRiskConfig,
    InstrumentPriceConstraints,
    compute_aggregated_brackets,
)


def _mk_risk(sl_pct: str, tp_rr: str) -> AggregatedOcoRiskConfig:
    return AggregatedOcoRiskConfig(
        sl_pct=Decimal(sl_pct),
        tp_rr=Decimal(tp_rr),
    )


def _mk_constraints(tick_size: str = "0.01", min_price: str = "0.01") -> InstrumentPriceConstraints:
    return InstrumentPriceConstraints(
        tick_size=Decimal(tick_size),
        min_price=Decimal(min_price),
    )


def test_long_brackets_basic():
    risk = _mk_risk("0.01", "2")  # SL=1%, TP=2% від entry
    constraints = _mk_constraints("0.01", "0.01")

    levels: AggregatedBracketLevels = compute_aggregated_brackets(
        position_amt=Decimal("1.0"),
        avg_entry_price=Decimal("100"),
        side="LONG",
        risk_cfg=risk,
        constraints=constraints,
    )

    # LONG:
    # SL = 100 * (1 - 0.01) = 99.00
    # TP = 100 * (1 + 0.01 * 2) = 102.00
    assert levels.sl_price == Decimal("99.00")
    assert levels.tp_price == Decimal("102.00")
    assert isinstance(levels.why, str)
    assert len(levels.why) <= 80


def test_short_brackets_basic():
    risk = _mk_risk("0.01", "2")  # SL=1%, TP=2% від entry
    constraints = _mk_constraints("0.01", "0.01")

    levels: AggregatedBracketLevels = compute_aggregated_brackets(
        position_amt=Decimal("1.0"),
        avg_entry_price=Decimal("100"),
        side="SHORT",
        risk_cfg=risk,
        constraints=constraints,
    )

    # SHORT:
    # SL = 100 * (1 + 0.01)       = 101.00
    # TP = 100 * (1 - 0.01 * 2)   = 98.00
    assert levels.sl_price == Decimal("101.00")
    assert levels.tp_price == Decimal("98.00")


def test_rounding_to_tick_size():
    risk = _mk_risk("0.013", "1.5")  # SL=1.3%, TP=1.95% від entry
    constraints = _mk_constraints("0.05", "0.05")  # грубий tick

    levels = compute_aggregated_brackets(
        position_amt=Decimal("1.0"),
        avg_entry_price=Decimal("100"),
        side="LONG",
        risk_cfg=risk,
        constraints=constraints,
    )

    # Сирі значення:
    # SL_raw = 100 * (1 - 0.013)        = 98.7
    # TP_raw = 100 * (1 + 0.013 * 1.5)  = 101.95
    # При tick_size=0.05 і ROUND_DOWN:
    # SL -> 98.65, TP -> 101.95 (і так кратні 0.05)
    assert levels.sl_price % constraints.tick_size == 0
    assert levels.tp_price % constraints.tick_size == 0
    assert levels.sl_price <= Decimal("98.70")
    assert levels.tp_price <= Decimal("101.95")


def test_min_price_enforced():
    risk = _mk_risk("0.50", "1")  # SL=50% від entry
    constraints = _mk_constraints("0.01", "10.00")

    levels = compute_aggregated_brackets(
        position_amt=Decimal("1.0"),
        avg_entry_price=Decimal("15.0"),
        side="LONG",
        risk_cfg=risk,
        constraints=constraints,
    )

    # SL_raw = 15 * (1 - 0.5) = 7.5 -> підтягується до min_price=10.0
    assert levels.sl_price == Decimal("10.00")
    assert levels.tp_price > levels.sl_price


@pytest.mark.parametrize(
    "position_amt, avg_price, sl_pct, tp_rr, tick_size, min_price",
    [
        (Decimal("0"), Decimal("100"), Decimal("0.01"),
         Decimal("2"), Decimal("0.01"), Decimal("0.01")),
        (Decimal("-1"), Decimal("100"), Decimal("0.01"),
         Decimal("2"), Decimal("0.01"), Decimal("0.01")),
        (Decimal("1"), Decimal("0"), Decimal("0.01"),
         Decimal("2"), Decimal("0.01"), Decimal("0.01")),
        (Decimal("1"), Decimal("100"), Decimal("0"),
         Decimal("2"), Decimal("0.01"), Decimal("0.01")),
        (Decimal("1"), Decimal("100"), Decimal("0.01"),
         Decimal("0"), Decimal("0.01"), Decimal("0.01")),
        (Decimal("1"), Decimal("100"), Decimal("0.01"),
         Decimal("2"), Decimal("0"), Decimal("0.01")),
        (Decimal("1"), Decimal("100"), Decimal("0.01"),
         Decimal("2"), Decimal("0.01"), Decimal("0")),
    ],
)
def test_invalid_inputs_raise(
    position_amt: Decimal,
    avg_price: Decimal,
    sl_pct: Decimal,
    tp_rr: Decimal,
    tick_size: Decimal,
    min_price: Decimal,
):
    risk = AggregatedOcoRiskConfig(sl_pct=sl_pct, tp_rr=tp_rr)
    constraints = InstrumentPriceConstraints(
        tick_size=tick_size, min_price=min_price)

    with pytest.raises(AggregatedOcoError):
        compute_aggregated_brackets(
            position_amt=position_amt,
            avg_entry_price=avg_price,
            side="LONG",
            risk_cfg=risk,
            constraints=constraints,
        )


def test_why_truncated_to_80_chars():
    risk = _mk_risk("0.01", "2")
    constraints = _mk_constraints()

    long_why = "x" * 200
    levels = compute_aggregated_brackets(
        position_amt=Decimal("1.0"),
        avg_entry_price=Decimal("100"),
        side="LONG",
        risk_cfg=risk,
        constraints=constraints,
        why=long_why,
    )

    assert len(levels.why) == 80
