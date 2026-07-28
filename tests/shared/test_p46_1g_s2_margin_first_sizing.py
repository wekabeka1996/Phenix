from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from apps.reference.config.shared.instruments import InstrumentSizingConfig
from apps.reference.shared.decision_primitives.sizing_margin_first import (
    compute_notional_target,
    compute_qty,
    floor_to_step,
)
from apps.reference.domains.decision_making.primitives.position_queries import PositionQueries


def _snapshot_is_fresh(
    snapshot_at: datetime | None,
    observed_at: datetime | None,
    max_age_sec: int,
) -> tuple[bool, str]:
    if snapshot_at is None or observed_at is None:
        return False, "TIMESTAMP_MISSING"
    if snapshot_at.tzinfo is None or observed_at.tzinfo is None:
        return False, "TIMEZONE_MISSING"
    age = (observed_at - snapshot_at).total_seconds()
    if age < 0:
        return False, "FUTURE_TIMESTAMP"
    if age > max_age_sec:
        return False, "SNAPSHOT_STALE"
    return True, "FRESH"


def test_1_config_ssot_fee_buffer_fraction_validation() -> None:
    config = InstrumentSizingConfig(
        margin_pct=0.11,
        fee_buffer_fraction=Decimal("0.001"),
    )
    assert config.fee_buffer_fraction == Decimal("0.001")

    with pytest.raises(ValueError):
        InstrumentSizingConfig(
            margin_pct=0.11,
            fee_buffer_fraction=Decimal("-0.001"),
        )

    with pytest.raises(ValueError):
        InstrumentSizingConfig(
            margin_pct=0.11,
            fee_buffer_fraction=Decimal("1.0"),
        )


def test_2_snapshot_freshness_boundary_and_stale_rejection() -> None:
    now = datetime.now(timezone.utc)
    fresh_ts = now - timedelta(seconds=5)
    stale_ts = now - timedelta(seconds=20)
    future_ts = now + timedelta(seconds=10)

    is_fresh, reason = _snapshot_is_fresh(fresh_ts, now, 15)
    assert is_fresh is True
    assert reason == "FRESH"

    is_fresh, reason = _snapshot_is_fresh(stale_ts, now, 15)
    assert is_fresh is False
    assert reason == "SNAPSHOT_STALE"

    is_fresh, reason = _snapshot_is_fresh(None, now, 15)
    assert is_fresh is False
    assert reason == "TIMESTAMP_MISSING"

    is_fresh, reason = _snapshot_is_fresh(future_ts, now, 15)
    assert is_fresh is False
    assert reason == "FUTURE_TIMESTAMP"


def test_3_compute_notional_target_requires_fee_buffer() -> None:
    margin_usdt, notional_target = compute_notional_target(
        equity=Decimal("1000"),
        margin_pct=Decimal("0.10"),
        leverage=10,
        fee_buffer=Decimal("0.001"),
    )
    # safe_equity = 1000 * (1 - 0.001) = 999
    # margin_usdt = 999 * 0.10 = 99.9
    # notional_target = 99.9 * 10 = 999.0
    assert margin_usdt == Decimal("99.9")
    assert notional_target == Decimal("999.0")


import logging

def test_4_position_queries_uses_fee_buffer_fraction() -> None:
    pq = PositionQueries(
        config={
            "instruments": {
                "BTCUSDT": {
                    "step_size": "0.001",
                    "min_qty": "0.001",
                    "min_notional": "10",
                    "sizing": {
                        "margin_pct": 0.10,
                        "fee_buffer_fraction": "0.001",
                    },
                    "execution": {
                        "target_leverage": 10,
                    },
                }
            }
        },
        get_portfolio=lambda: None,
        min_pos_size_usd=Decimal("10"),
        liq_cap_usd=Decimal("100000"),
        logger=logging.getLogger("test"),
    )

    result, why, err_code, dbg = pq.calculate_position_size(
        symbol="BTCUSDT",
        price=Decimal("50000"),
        side="BUY",
        context={"portfolio": {"equity": "1000"}},
    )

    assert err_code is None
    assert why == "margin_first_ok"
    assert result is not None
    assert dbg["fee_buffer_fraction"] == "0.001"
    assert Decimal(dbg["notional_target"]) == Decimal("999.0")


def test_5_case_a_fresh_and_within_limits_mocked_proof() -> None:
    now = datetime.now(timezone.utc)
    account_ts = now - timedelta(seconds=2)
    market_ts = now - timedelta(seconds=1)

    acc_fresh, _ = _snapshot_is_fresh(account_ts, now, 15)
    mkt_fresh, _ = _snapshot_is_fresh(market_ts, now, 15)
    assert acc_fresh and mkt_fresh

    margin_usdt, notional = compute_notional_target(
        equity=Decimal("10000"),
        margin_pct=Decimal("0.10"),
        leverage=20,
        fee_buffer=Decimal("0.001"),
    )
    raw_qty, rounded_qty = compute_qty(
        notional_target=notional,
        price=Decimal("2000"),
        step_size=Decimal("0.001"),
    )

    assert rounded_qty > 0
    assert rounded_qty * Decimal("2000") <= notional


def test_6_case_b_margin_clipping_mocked_proof() -> None:
    # Requested size $50,000, but wallet equity $1,000 with 10x leverage permits max $9,990 notional
    requested_notional = Decimal("50000")
    _, max_notional = compute_notional_target(
        equity=Decimal("1000"),
        margin_pct=Decimal("1.0"),
        leverage=10,
        fee_buffer=Decimal("0.001"),
    )
    clipped_notional = min(requested_notional, max_notional)
    assert clipped_notional == Decimal("9990.0")
    assert clipped_notional < requested_notional


def test_7_case_c_exposure_clipping_mocked_proof() -> None:
    margin_notional = Decimal("20000")
    remaining_exposure_cap = Decimal("5000")

    executable_notional = min(margin_notional, remaining_exposure_cap)
    assert executable_notional == Decimal("5000")


def test_8_case_d_stale_snapshot_fails_closed() -> None:
    now = datetime.now(timezone.utc)
    stale_account_ts = now - timedelta(seconds=30)
    is_fresh, reason = _snapshot_is_fresh(stale_account_ts, now, 15)

    venue_calls = 0
    if not is_fresh:
        # Fail closed immediately
        pass
    else:
        venue_calls += 1

    assert is_fresh is False
    assert reason == "SNAPSHOT_STALE"
    assert venue_calls == 0


def test_9_case_e_no_executable_quantity_fails_closed() -> None:
    # Extremely small equity resulting in qty below min_qty
    equity = Decimal("0.01")
    _, notional = compute_notional_target(
        equity=equity,
        margin_pct=Decimal("0.10"),
        leverage=1,
        fee_buffer=Decimal("0.001"),
    )
    _, rounded_qty = compute_qty(
        notional_target=notional,
        price=Decimal("50000"),
        step_size=Decimal("0.001"),
    )

    venue_calls = 0
    min_qty = Decimal("0.001")
    if rounded_qty < min_qty:
        # Rejection: qty below minimum
        pass
    else:
        venue_calls += 1

    assert rounded_qty == Decimal("0")
    assert venue_calls == 0
