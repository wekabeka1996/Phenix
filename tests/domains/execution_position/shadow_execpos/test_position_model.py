import math
from apps.reference.domains.execution_position.shadow_execpos.position_model import (
    PositionState,
    apply_fill,
)


def almost_eq(a, b, eps=1e-9):
    return abs(a - b) < eps


def test_scale_in_updates_avg_price():
    state = PositionState(symbol="BTCUSDT")
    state = apply_fill(state, side="BUY", quantity=1, price=100)
    state = apply_fill(state, side="BUY", quantity=1, price=200)

    assert almost_eq(state.qty, 2.0)
    assert almost_eq(state.avg_entry_price, 150.0)
    assert state.scale_in_count == 1


def test_partial_close_updates_realized_pnl_and_qty():
    state = PositionState(symbol="BTCUSDT")
    state = apply_fill(state, side="BUY", quantity=2, price=100)
    state = apply_fill(state, side="SELL", quantity=1, price=150)

    assert almost_eq(state.qty, 1.0)
    assert almost_eq(state.realized_pnl, 50.0)  # (150-100) * 1
    assert state.scale_out_count == 1
    # avg price unchanged for remaining long
    assert almost_eq(state.avg_entry_price, 100.0)


def test_flip_resets_avg_price_and_counts():
    state = PositionState(symbol="BTCUSDT")
    state = apply_fill(state, side="BUY", quantity=1, price=100)
    state = apply_fill(state, side="SELL", quantity=2, price=90)  # close 1, open 1 short

    assert almost_eq(state.qty, -1.0)
    assert almost_eq(state.realized_pnl, -10.0)  # long closed at loss (90-100)
    assert almost_eq(state.avg_entry_price, 90.0)  # new short entry price
    assert state.scale_in_count == 0
    assert state.scale_out_count == 1
    assert state.side == "SHORT"

