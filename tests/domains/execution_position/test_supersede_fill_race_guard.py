from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vfoundation.core.protocol import Message


def _queued_open_decision(symbol: str = "BTCUSDT") -> Message:
    return Message(
        op="DEC",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid=f"rid_supersede_{symbol}",
        pld={
            "symbol": symbol,
            "side": "BUY",
            "qty": "0.001",
            "order_type": "MARKET",
        },
        why="test_supersede_replay",
    )


def _seed_supersede_queue(fsm, symbol: str, decision: Message) -> None:
    fsm._supersede_canceling = {symbol}
    fsm._supersede_queue = {
        symbol: {
            "decision": decision,
            "queued_at": 0.0,
        }
    }


@pytest.mark.asyncio
async def test_supersede_timeout_blocks_open_when_live_position_exists(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    decision = _queued_open_decision(symbol)
    _seed_supersede_queue(fsm, symbol, decision)

    fsm.adapter = MagicMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": symbol, "positionAmt": "0.010"}]
    )
    fsm._execute_decision = AsyncMock()

    with patch("apps.reference.domains.execution_position.fsm.LOG.warning") as warn_mock:
        await fsm._process_queued_supersede(symbol)

    fsm._execute_decision.assert_not_called()
    warnings = [str(call.args[0]) for call in warn_mock.call_args_list if call.args]
    assert any(
        "EP-01.3 supersede aborted: position already open" in msg and symbol in msg
        for msg in warnings
    )


@pytest.mark.asyncio
async def test_supersede_timeout_blocks_open_when_position_query_unavailable_fail_closed(
    fsm_harness,
):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    decision = _queued_open_decision(symbol)
    _seed_supersede_queue(fsm, symbol, decision)

    fsm.adapter = MagicMock()
    fsm.adapter.get_open_positions = AsyncMock(side_effect=RuntimeError("positionRisk down"))
    fsm._execute_decision = AsyncMock()

    with patch("apps.reference.domains.execution_position.fsm.LOG.warning") as warn_mock:
        await fsm._process_queued_supersede(symbol)

    fsm._execute_decision.assert_not_called()
    warnings = [str(call.args[0]) for call in warn_mock.call_args_list if call.args]
    assert any(
        "EP-01.3 supersede aborted: position check unavailable" in msg and symbol in msg
        for msg in warnings
    )


@pytest.mark.asyncio
async def test_supersede_timeout_allows_open_when_no_live_position(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    decision = _queued_open_decision(symbol)
    _seed_supersede_queue(fsm, symbol, decision)

    fsm.adapter = MagicMock()
    fsm.adapter.get_open_positions = AsyncMock(return_value=[])
    fsm._execute_decision = AsyncMock()

    await fsm._process_queued_supersede(symbol)

    fsm._execute_decision.assert_called_once_with(decision)


@pytest.mark.asyncio
async def test_process_queued_supersede_does_not_reference_missing_async_method(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    decision = _queued_open_decision(symbol)
    _seed_supersede_queue(fsm, symbol, decision)

    assert not hasattr(fsm, "_async_execute_decision")

    fsm.adapter = MagicMock()
    fsm.adapter.get_open_positions = AsyncMock(return_value=[])
    fsm._execute_decision = AsyncMock()

    await fsm._process_queued_supersede(symbol)

    fsm._execute_decision.assert_called_once_with(decision)
