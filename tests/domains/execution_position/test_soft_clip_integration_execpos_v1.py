import time
from decimal import Decimal

from vfoundation.core.protocol import Message


def test_execpos_exposure_guard_soft_clip_scales_qty(fsm_harness):
    fsm, _bus, _cfg = fsm_harness

    # Make hard gates non-binding for this test (we only want to exercise soft-limit clipping).
    fsm.exposure_guard.max_portfolio_fraction = Decimal("1000")

    now_ms = int(time.time() * 1000)
    fsm._latest_portfolio_state = {
        "positions_last_ts_ms": now_ms,
        "equity_free_usdt": "10000",
        # Balanced long/short so side_exposure_usdt is not already breached.
        "positions_by_side": {"long_margin": "525", "short_margin": "525"},
        "open_positions_margin_usd": "1050",
        "open_positions_usd": "0",
        "positions": [],
    }

    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="rid_clip_1",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "1",
            "price_ref": "10000",
            "idempotent_key": "idem_clip_1",
        },
        why="test",
    )

    err = fsm._check_exposure_fail_closed(msg)
    assert err is None

    # Requested notional = 1 * 10000 = 10000
    # With total margin=1050 and margin_exposure_usdt=1100, extra margin=50.
    # With leverage=20, clipped notional should be ~1000.
    assert Decimal(msg.pld["qty"]) == Decimal("0.1")
    assert "exposure_clip" in msg.pld
    assert Decimal(msg.pld["exposure_clip"]["clipped_notional_abs"]) == Decimal("1000")

    # Reservation should reflect clipped notional (fail-closed accounting).
    pending = fsm.exposure_guard.state.pending_exposure["idem_clip_1"]
    assert pending["notional"] == Decimal("1000")
