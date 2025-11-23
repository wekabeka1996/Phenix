from apps.reference.domains.execution_position.shadow_execpos.trailing import (
    TrailingStopService,
    TrailingConfig,
    TrailingState,
)
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState


def test_trailing_sets_sl_for_long():
    svc = TrailingStopService()
    pos = PositionState(symbol="BTCUSDT", qty=1.0, avg_entry_price=100.0)
    cfg = TrailingConfig(trail_distance_bps=100.0)  # 1%
    state = TrailingState()

    dec = svc.eval_trailing(position=pos, price=110.0, trail_state=state, cfg=cfg, now=0)

    assert not dec.exit
    assert dec.sl_price == 110.0 * 0.99  # 1% trail
    assert dec.trail_state.status in ("ACTIVE", "BREAKEVEN", "EXIT_SIGNAL")


def test_breakeven_moves_sl_to_entry():
    svc = TrailingStopService()
    pos = PositionState(symbol="BTCUSDT", qty=1.0, avg_entry_price=100.0)
    cfg = TrailingConfig(trail_distance_bps=100.0, breakeven_rr=2)  # breakeven after 2% move
    state = TrailingState()

    dec = svc.eval_trailing(position=pos, price=103.0, trail_state=state, cfg=cfg, now=0)

    assert dec.trail_state.breakeven_hit is True
    assert dec.sl_price == 100.0  # moved to entry
    assert not dec.exit


def test_trailing_exit_when_price_hits_sl():
    svc = TrailingStopService()
    pos = PositionState(symbol="BTCUSDT", qty=1.0, avg_entry_price=100.0)
    cfg = TrailingConfig(trail_distance_bps=100.0)
    # Prime state with higher watermark and SL
    primed = svc.eval_trailing(position=pos, price=110.0, trail_state=TrailingState(), cfg=cfg, now=0)
    state = primed.trail_state

    dec = svc.eval_trailing(position=pos, price=state.sl_price - 0.1, trail_state=state, cfg=cfg, now=1)

    assert dec.exit is True
    assert dec.reason_code == "TRAIL_HIT"
    assert dec.trail_state.status == "EXIT_SIGNAL"


def test_time_exit_triggers_exit():
    svc = TrailingStopService()
    pos = PositionState(symbol="BTCUSDT", qty=1.0, avg_entry_price=100.0, open_time=0.0)
    cfg = TrailingConfig(trail_distance_bps=100.0, hard_time_exit_sec=10.0)
    state = TrailingState()

    dec = svc.eval_trailing(position=pos, price=101.0, trail_state=state, cfg=cfg, now=11.0)

    assert dec.exit is True
    assert dec.reason_code == "TIME_EXIT"
