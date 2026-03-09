from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.fsm import PendingEntryMeta


def _limit_open_decision(symbol: str, side: str, price: str) -> Message:
    return Message(
        op="DEC",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid=f"rid_{symbol}_{side}_{price}",
        pld={
            "symbol": symbol,
            "side": side,
            "qty": "0.010",
            "order_type": "LIMIT",
            "price": price,
        },
        why="test_supersede_reprice_guard",
    )


def _seed_pending_order(fsm, symbol: str, side: str, order_id: str, limit_price: str) -> None:
    fsm.adapter = MagicMock()
    fsm.adapter.base_url = "https://testnet.binance.example"
    fsm.watchdog = MagicMock()
    fsm.watchdog.pending_orders = {order_id: SimpleNamespace(symbol=symbol, rid=f"rid_{order_id}")}
    fsm.watchdog.acked_orders = {}
    fsm._pending_entry_meta[order_id] = PendingEntryMeta(
        symbol=symbol,
        side=side,
        limit_price=limit_price,
        placed_at_ms=0,
        tf_sec=300,
        cancelable_regimes=None,
    )
    fsm._supersede_canceling = set()
    fsm._supersede_queue = {}
    fsm._cancel_pending_entries_for_symbol = MagicMock()
    fsm._submit_async = MagicMock()
    fsm._get_async_loop = MagicMock(return_value=MagicMock())
    fsm._last_features_cache[symbol] = {"features": {"atr_14": "5.0"}}


def _enable_guard(fsm, enforce: bool) -> None:
    pe_cfg = fsm.config.domains.execution_position.pending_entry_ttl
    pe_cfg.enabled = True
    pe_cfg.cancel_on_supersede = True
    pe_cfg.supersede_cancel_timeout_sec = 5.0
    pe_cfg.supersede_reprice_guard = SimpleNamespace(
        enabled=True,
        enforce=enforce,
        min_price_improvement_bps=5.0,
        min_price_improvement_atr_mult=0.1,
    )


@pytest.mark.asyncio
async def test_supersede_reprice_guard_shadow_logs_but_keeps_current_behavior(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    order_id = "ord_keep_shadow"
    _seed_pending_order(fsm, symbol, "BUY", order_id, "2000.00")
    _enable_guard(fsm, enforce=False)

    decision = _limit_open_decision(symbol, "BUY", "2000.80")  # +4 bps improvement

    with patch("apps.reference.domains.execution_position.fsm.order_logger.write") as write_mock:
        await fsm._execute_decision(decision)

    fsm._cancel_pending_entries_for_symbol.assert_called_once()
    events = [call.args[0] for call in write_mock.call_args_list if call.args]
    assert any(
        evt.get("event_type") == "ORDER_SUPERSEDE_REPRICE_ANALYZED"
        and evt.get("mode") == "shadow"
        and evt.get("noop_candidate") is True
        for evt in events
    )


@pytest.mark.asyncio
async def test_supersede_reprice_guard_enforce_skips_cancel_for_tiny_improvement(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    order_id = "ord_keep_enforce"
    _seed_pending_order(fsm, symbol, "BUY", order_id, "2000.00")
    _enable_guard(fsm, enforce=True)

    decision = _limit_open_decision(symbol, "BUY", "2000.80")  # +4 bps improvement

    with patch("apps.reference.domains.execution_position.fsm.order_logger.write") as write_mock:
        await fsm._execute_decision(decision)

    fsm._cancel_pending_entries_for_symbol.assert_not_called()
    assert symbol not in fsm._supersede_canceling
    assert symbol not in fsm._supersede_queue
    events = [call.args[0] for call in write_mock.call_args_list if call.args]
    assert any(
        evt.get("event_type") == "ORDER_SUPERSEDE_REPRICE_ANALYZED"
        and evt.get("mode") == "enforce"
        and evt.get("noop_candidate") is True
        for evt in events
    )


@pytest.mark.asyncio
async def test_supersede_reprice_guard_allows_cancel_for_real_improvement(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    order_id = "ord_reprice_real"
    _seed_pending_order(fsm, symbol, "SELL", order_id, "2000.00")
    _enable_guard(fsm, enforce=True)

    decision = _limit_open_decision(symbol, "SELL", "1998.60")  # ~7 bps more aggressive

    with patch("apps.reference.domains.execution_position.fsm.order_logger.write") as write_mock:
        await fsm._execute_decision(decision)

    fsm._cancel_pending_entries_for_symbol.assert_called_once()
    events = [call.args[0] for call in write_mock.call_args_list if call.args]
    assert any(
        evt.get("event_type") == "ORDER_SUPERSEDE_REPRICE_ANALYZED"
        and evt.get("noop_candidate") is False
        for evt in events
    )
