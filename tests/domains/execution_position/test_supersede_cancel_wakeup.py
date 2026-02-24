from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.idempotent_cancel import (
    IdempotentCancelResult,
)


def _queued_decision(symbol: str) -> Message:
    return Message(
        op="DEC",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid=f"rid_{symbol}",
        pld={"symbol": symbol, "side": "BUY", "qty": "0.001", "order_type": "MARKET"},
        why="test_supersede_wakeup",
    )


async def _run_scheduled_cancel_task(fsm) -> None:
    # _cancel_pending_entries_for_symbol schedules _do_cancel via _submit_async.
    assert fsm._submit_async.call_count >= 1
    cancel_coro = fsm._submit_async.call_args_list[0].args[0]
    await cancel_coro

    # If wake-up scheduled a supersede drain, run it too so assertions can observe calls.
    if fsm._submit_async.call_count >= 2:
        drain_coro = fsm._submit_async.call_args_list[1].args[0]
        await drain_coro


@pytest.mark.asyncio
async def test_cancel_success_wakes_supersede_drain_immediately(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    order_id = "ord_ok_1"
    deadline = SimpleNamespace(symbol=symbol, rid="rid_ok")

    fsm.watchdog = MagicMock()
    fsm.watchdog.pending_orders = {order_id: deadline}
    fsm.watchdog.acked_orders = {}
    fsm.adapter = MagicMock()
    fsm.shadow_mode = False
    fsm._cancel_order = AsyncMock(
        return_value=IdempotentCancelResult(
            success=True,
            reason="CANCEL_SUCCESS",
            is_idempotent_success=False,
        )
    )
    fsm._submit_async = MagicMock()
    fsm._process_queued_supersede = AsyncMock()
    fsm._supersede_canceling = {symbol}
    fsm._supersede_queue = {symbol: {"decision": _queued_decision(symbol), "queued_at": 0.0}}

    with patch("apps.reference.domains.execution_position.fsm.order_logger.write"):
        fsm._cancel_pending_entries_for_symbol(
            symbol=symbol,
            reason="CANCEL_SUPERSEDED",
            context="test_ctx",
        )
        await _run_scheduled_cancel_task(fsm)

    fsm._process_queued_supersede.assert_called_once_with(symbol)


@pytest.mark.asyncio
async def test_cancel_failed_does_not_wake_drain(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    order_id = "ord_fail_1"
    deadline = SimpleNamespace(symbol=symbol, rid="rid_fail")

    fsm.watchdog = MagicMock()
    fsm.watchdog.pending_orders = {order_id: deadline}
    fsm.watchdog.acked_orders = {}
    fsm.adapter = MagicMock()
    fsm.shadow_mode = False
    fsm._cancel_order = AsyncMock(
        return_value=IdempotentCancelResult(
            success=False,
            reason="EXCEPTION_AFTER_2_RETRIES",
            is_idempotent_success=False,
        )
    )
    fsm._submit_async = MagicMock()
    fsm._process_queued_supersede = AsyncMock()
    fsm._supersede_canceling = {symbol}
    fsm._supersede_queue = {symbol: {"decision": _queued_decision(symbol), "queued_at": 0.0}}

    with patch("apps.reference.domains.execution_position.fsm.order_logger.write"):
        fsm._cancel_pending_entries_for_symbol(
            symbol=symbol,
            reason="CANCEL_SUPERSEDED",
            context="test_ctx",
        )
        await _run_scheduled_cancel_task(fsm)

    fsm._process_queued_supersede.assert_not_called()
    # Only _do_cancel should be scheduled.
    assert fsm._submit_async.call_count == 1


@pytest.mark.asyncio
async def test_cancel_idempotent_success_wakes_drain(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    order_id = "ord_idemp_1"
    deadline = SimpleNamespace(symbol=symbol, rid="rid_idemp")

    fsm.watchdog = MagicMock()
    fsm.watchdog.pending_orders = {order_id: deadline}
    fsm.watchdog.acked_orders = {}
    fsm.adapter = MagicMock()
    fsm.shadow_mode = False
    fsm._cancel_order = AsyncMock(
        return_value=IdempotentCancelResult(
            success=False,
            reason="IDEMPOTENT_-2011_ABSORBED_EXC",
            is_idempotent_success=True,
        )
    )
    fsm._submit_async = MagicMock()
    fsm._process_queued_supersede = AsyncMock()
    fsm._supersede_canceling = {symbol}
    fsm._supersede_queue = {symbol: {"decision": _queued_decision(symbol), "queued_at": 0.0}}

    with patch("apps.reference.domains.execution_position.fsm.order_logger.write"):
        fsm._cancel_pending_entries_for_symbol(
            symbol=symbol,
            reason="CANCEL_SUPERSEDED",
            context="test_ctx",
        )
        await _run_scheduled_cancel_task(fsm)

    fsm._process_queued_supersede.assert_called_once_with(symbol)
