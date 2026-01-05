from __future__ import annotations

from unittest.mock import patch

from vfoundation.core.protocol import Message


def _portfolio_evt(positions: list[dict], *, positions_last_ts_ms: int = 0) -> Message:
    return Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="portfolio",
        dst="execution_position",
        rid="rid-portfolio",
        pld={
            "equity_free_usdt": "1000",
            "equity_cross_usdt": "1000",
            "positions": positions,
            "positions_last_ts_ms": positions_last_ts_ms,
        },
    )


def _cmd_open(rid: str = "rid-open", symbol: str = "BTCUSDT") -> Message:
    return Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid=rid,
        pld={
            "symbol": symbol,
            "side": "BUY",
            "order_type": "MARKET",
            "qty": "0.001",
            "price_ref": "10000",
            "idempotent_key": rid,
        },
    )


def test_execpos_blocks_open_during_global_cooldown_after_close(fsm_harness) -> None:
    fsm, _bus, _cfg = fsm_harness

    # Position is open in snapshot.
    with patch("apps.reference.domains.execution_position.fsm.time.time", return_value=1000.0):
        fsm.handle(
            _portfolio_evt(
                [{"symbol": "BTCUSDT", "positionAmt": "1.0"}],
                positions_last_ts_ms=1_000_000,
            )
        )

    # Next snapshot: position disappears => close detected at t=1000.
    with patch("apps.reference.domains.execution_position.fsm.time.time", return_value=1000.0):
        fsm.handle(_portfolio_evt([], positions_last_ts_ms=1_000_000))

    # Try to open at t=1005 (< 10s cooldown) => blocked.
    with patch("apps.reference.domains.execution_position.fsm.time.time", return_value=1005.0):
        out = fsm.handle(_cmd_open(rid="rid-open-1"))

    assert out is not None
    assert out.op == "ERR" and out.verb == "OPEN"
    assert out.why == "OPEN_GUARD_FAIL"
    assert out.pld.get("reason") == "cooldown_after_close active"


def test_execpos_allows_open_after_global_post_close_cooldown_expires(fsm_harness) -> None:
    fsm, _bus, _cfg = fsm_harness

    with patch("apps.reference.domains.execution_position.fsm.time.time", return_value=1000.0):
        fsm.handle(
            _portfolio_evt(
                [{"symbol": "BTCUSDT", "positionAmt": "1.0"}],
                positions_last_ts_ms=1_000_000,
            )
        )
        fsm.handle(_portfolio_evt([], positions_last_ts_ms=1_000_000))

    # Refresh portfolio timestamp so exposure guard isn't stale at open time.
    with patch("apps.reference.domains.execution_position.fsm.time.time", return_value=1011.0):
        fsm.handle(_portfolio_evt([], positions_last_ts_ms=1_011_000))

    # After cooldown, open returns DEC:OPEN (shadow-mode doesn't execute).
    with patch("apps.reference.domains.execution_position.fsm.time.time", return_value=1011.0):
        out = fsm.handle(_cmd_open(rid="rid-open-2"))

    assert out is not None
    assert out.op == "DEC" and out.verb == "OPEN"
