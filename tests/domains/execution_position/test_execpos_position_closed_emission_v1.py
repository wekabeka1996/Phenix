from __future__ import annotations

import asyncio
import logging

import pytest

from vfoundation.core.protocol import Message


def _portfolio_event(
    positions: list[dict],
    *,
    realized_pnl: str,
    ts_ms: int,
    fees: str = "0.0",
    rid: str = "rid-portfolio",
) -> Message:
    return Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="position_tracking",
        dst="execution_position",
        rid=rid,
        pld={
            "positions": positions,
            "realized_pnl": realized_pnl,
            "ts": ts_ms,
            "fees": fees,
            "equity_free_usdt": "1000",
            "equity_cross_usdt": "1000",
        },
    )


def _extract_position_closed_events(bus) -> list[tuple]:
    return [evt for evt in bus.events if evt[0] == "EVT:POSITION_CLOSED"]


def test_emits_position_closed_with_structured_payload(fsm_harness) -> None:
    fsm, bus, _cfg = fsm_harness

    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [{"symbol": "BTCUSDT", "positionAmt": "0.5"}],
            realized_pnl="100.0",
            ts_ms=1_700_000_000_000,
        )
    )
    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [{"symbol": "BTCUSDT", "positionAmt": "0.0"}],
            realized_pnl="103.5",
            ts_ms=1_700_000_001_000,
            rid="rid-close",
        )
    )

    close_events = _extract_position_closed_events(bus)
    assert len(close_events) == 1

    _, args, _kwargs = close_events[0]
    payload = args[0]
    assert payload["symbol"] == "BTCUSDT"
    assert payload["trade_id"].startswith("BTCUSDT:1700000001000:")
    assert payload["close_ts_ms"] == 1_700_000_001_000
    assert payload["realized_pnl_net"] == pytest.approx(3.5)
    assert payload["fees"] == pytest.approx(0.0)
    assert payload["event_type"] == "POSITION_CLOSED"


def test_splits_realized_delta_when_multiple_symbols_close_together(fsm_harness) -> None:
    fsm, bus, _cfg = fsm_harness

    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [
                {"symbol": "BTCUSDT", "positionAmt": "0.3"},
                {"symbol": "ETHUSDT", "positionAmt": "-1.2"},
            ],
            realized_pnl="50.0",
            ts_ms=1_700_000_010_000,
        )
    )
    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [
                {"symbol": "BTCUSDT", "positionAmt": "0.0"},
                {"symbol": "ETHUSDT", "positionAmt": "0.0"},
            ],
            realized_pnl="54.0",
            ts_ms=1_700_000_011_000,
            fees="1.2",
        )
    )

    close_events = _extract_position_closed_events(bus)
    assert len(close_events) == 2

    for _, args, _kwargs in close_events:
        payload = args[0]
        assert payload["realized_pnl_net"] == pytest.approx(2.0)
        assert payload["fees"] == pytest.approx(0.6)
        assert payload["close_ts_ms"] == 1_700_000_011_000


@pytest.mark.asyncio
async def test_position_closed_emits_once_on_async_loop_path(fsm_harness) -> None:
    fsm, bus, _cfg = fsm_harness

    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [{"symbol": "BTCUSDT", "positionAmt": "0.5"}],
            realized_pnl="10.0",
            ts_ms=1_700_000_100_000,
        )
    )
    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [{"symbol": "BTCUSDT", "positionAmt": "0.0"}],
            realized_pnl="12.0",
            ts_ms=1_700_000_101_000,
            rid="rid-close-async",
        )
    )
    await asyncio.sleep(0.01)

    close_events = _extract_position_closed_events(bus)
    assert len(close_events) == 1


def test_logs_structured_position_closed_line_for_core_parser(fsm_harness, caplog) -> None:
    fsm, _bus, _cfg = fsm_harness
    caplog.set_level(logging.INFO)

    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [{"symbol": "BTCUSDT", "positionAmt": "0.5"}],
            realized_pnl="10.0",
            ts_ms=1_700_000_200_000,
        )
    )
    fsm._on_portfolio_state_updated(
        _portfolio_event(
            [{"symbol": "BTCUSDT", "positionAmt": "0.0"}],
            realized_pnl="12.5",
            ts_ms=1_700_000_201_000,
            rid="rid-close-log",
        )
    )

    log_messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "EVT:POSITION_CLOSED symbol=BTCUSDT" in log_messages
    assert "trade_id=BTCUSDT:1700000201000:" in log_messages
    assert "close_ts_ms=1700000201000" in log_messages
    assert "realized_pnl_net=2.5" in log_messages
    assert "fees=" in log_messages
