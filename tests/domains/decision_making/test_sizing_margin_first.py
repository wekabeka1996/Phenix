import pytest
from decimal import Decimal


def test_margin_first_sizing_btc_x80_rounding_and_constraints_ok():
    from apps.reference.domains.decision_making.sizing_margin_first import (
        compute_notional_target,
        compute_qty,
        validate_exchange_constraints,
    )

    equity = Decimal("71.62")
    margin_pct = Decimal("0.09")
    leverage = 80

    margin_usdt, notional_target = compute_notional_target(
        equity=equity,
        margin_pct=margin_pct,
        leverage=leverage,
        notional_cap=None,
    )

    assert margin_usdt == Decimal("6.4393542")
    assert notional_target == Decimal("515.148336")

    raw_qty, rounded_qty = compute_qty(
        notional_target=notional_target,
        price=Decimal("88000"),
        step_size=Decimal("0.001"),
    )

    assert raw_qty > rounded_qty
    assert rounded_qty == Decimal("0.005")

    code, why = validate_exchange_constraints(
        qty=rounded_qty,
        price=Decimal("88000"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("100"),
    )
    assert (code, why) == (None, "ok")


def test_margin_first_sizing_can_fail_min_notional_due_to_step_floor():
    from apps.reference.domains.decision_making.sizing_margin_first import (
        compute_notional_target,
        compute_qty,
        validate_exchange_constraints,
    )

    # Low equity case: theoretical notional looks fine, but rounding down to step makes
    # final notional fall below min_notional.
    equity = Decimal("20")
    margin_pct = Decimal("0.09")
    leverage = 80

    _, notional_target = compute_notional_target(
        equity=equity,
        margin_pct=margin_pct,
        leverage=leverage,
        notional_cap=None,
    )

    _, rounded_qty = compute_qty(
        notional_target=notional_target,
        price=Decimal("88000"),
        step_size=Decimal("0.001"),
    )

    assert rounded_qty == Decimal("0.001")

    code, _ = validate_exchange_constraints(
        qty=rounded_qty,
        price=Decimal("88000"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("100"),
    )

    assert code == "MIN_NOTIONAL"


def test_compute_notional_target_rejects_invalid_inputs():
    from apps.reference.domains.decision_making.sizing_margin_first import compute_notional_target

    with pytest.raises(ValueError):
        compute_notional_target(equity=Decimal(
            "0"), margin_pct=Decimal("0.1"), leverage=10)
    with pytest.raises(ValueError):
        compute_notional_target(equity=Decimal(
            "10"), margin_pct=Decimal("0"), leverage=10)
    with pytest.raises(ValueError):
        compute_notional_target(equity=Decimal(
            "10"), margin_pct=Decimal("1.1"), leverage=10)
    with pytest.raises(ValueError):
        compute_notional_target(equity=Decimal(
            "10"), margin_pct=Decimal("0.1"), leverage=0)


@pytest.mark.parametrize("bad_fee_buffer", [Decimal("-0.01"), Decimal("1")])
def test_margin_first_helpers_reject_invalid_fee_buffer(bad_fee_buffer):
    from apps.reference.domains.decision_making.sizing_margin_first import (
        compute_exposure_based_qty,
        compute_notional_target,
    )

    with pytest.raises(ValueError, match="fee_buffer"):
        compute_notional_target(
            equity=Decimal("10"),
            margin_pct=Decimal("0.1"),
            leverage=10,
            fee_buffer=bad_fee_buffer,
        )

    with pytest.raises(ValueError, match="fee_buffer"):
        compute_exposure_based_qty(
            equity=Decimal("10"),
            exposure=0.5,
            leverage=10,
            price=Decimal("100"),
            step_size=Decimal("0.01"),
            fee_buffer=bad_fee_buffer,
        )
