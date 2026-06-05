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


def test_execpos_sidecar_close_emits_execution_submitted_state(fsm_harness):
    fsm, bus, cfg = fsm_harness

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
        rid="ppsreq:BTCUSDT:close-1",
        why="position_policy_sidecar_soft_close",
        pld={
            "symbol": "BTCUSDT",
            "reduce_only": True,
            "policy_context": {
                "symbol": "BTCUSDT",
                "policy_source": "position_policy_sidecar",
                "source_event_type": "POSITION_POLICY_SIDECAR_RECOMMENDED",
                "source_trace_id": "pps:BTCUSDT:1:1",
                "request_id": "ppsreq:BTCUSDT:close-1",
                "request_event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
                "requested_action": "SOFT_CLOSE",
                "requested_qty": None,
                "target_mode": "symbol_current_net_only",
                "allowed_action_scope": {
                    "soft_close_symbol_current_net_only": True,
                    "partial_reduce": False,
                    "bracket_mutation": False,
                    "exact_targeting": False,
                },
                "reason_codes": ["trigger:regime_detected", "recommend_soft_close_threshold_met"],
                "score_snapshot": {"soft_close_pressure": 0.6},
                "position_snapshot": {"symbol": "BTCUSDT", "side": "BUY"},
                "feature_ref": {},
                "regime_ref": {},
                "freshness_snapshot": {},
                "fill_correlation": {},
                "portfolio_correlation": {},
                "action_package_version": "phase2_action_package_v1",
                "request_ts_ms": 1_000_000,
            },
        },
    )

    async def _run():
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
    state_events = [
        args[0]
        for topic, args, _kwargs in bus.events
        if topic == "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE"
    ]
    assert len(state_events) == 1
    assert state_events[0]["request_state"] == "execution_submitted"
    assert state_events[0]["request_id"] == "ppsreq:BTCUSDT:close-1"
    assert state_events[0]["trace_id"] == "pps:BTCUSDT:1:1"
    assert state_events[0]["execution_close_side"] == "SELL"
    assert state_events[0]["execution_close_qty"] == "1.0"

