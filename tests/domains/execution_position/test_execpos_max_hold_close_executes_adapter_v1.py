from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from vfoundation.core.protocol import Message


def test_execpos_close_executes_reduce_only_market_via_adapter(fsm_harness):
    fsm, _bus, cfg = fsm_harness

    # Ensure guardrail allows adapter execution in test.
    cfg.get_domain_mode.return_value = "testnet"  # type: ignore[attr-defined]

    adapter = AsyncMock()
    adapter.base_url = "https://testnet.binancefuture.com"
    adapter.get_open_positions.return_value = [{"symbol": "BTCUSDT", "positionAmt": "1.0"}]
    adapter.get_open_orders.return_value = []

    fsm.adapter = adapter
    fsm.shadow_mode = False

    decision = Message(
        op="DEC",
        verb="CLOSE",
        src="execution_position",
        dst="execution_position",
        rid="rid-max-hold",
        why="max_hold_timeout",
        pld={"symbol": "BTCUSDT", "reduce_only": True},
    )

    async def _run():
        # Avoid slow sleeps inside DEC:CLOSE reconcile path.
        fsm_sleep = AsyncMock()
        import apps.reference.domains.execution_position.fsm as fsm_mod

        orig_sleep = fsm_mod.asyncio.sleep
        fsm_mod.asyncio.sleep = fsm_sleep
        try:
            await fsm._execute_decision(decision)
        finally:
            fsm_mod.asyncio.sleep = orig_sleep

    asyncio.run(_run())

    adapter.place_market_reduce_only.assert_awaited()
    args, kwargs = adapter.place_market_reduce_only.await_args
    assert args[0] == "BTCUSDT"
    assert args[1] == "SELL"  # positive positionAmt => SELL to close
    assert args[2] == "1.0"
    assert "new_client_order_id" in kwargs

