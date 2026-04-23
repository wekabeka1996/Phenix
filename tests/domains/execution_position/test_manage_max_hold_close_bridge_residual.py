from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from apps.reference.core.time import MockClock, reset_clock, set_clock
from apps.reference.domains.execution_position.close_producer_bridge import (
    CLOSE_PRODUCER_BRIDGE_CONTRACT,
)
from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM
from apps.reference.domains.execution_position.manage_max_hold_close_bridge import (
    MANAGE_MAX_HOLD_CLOSE_CONTRACT,
    MANAGE_MAX_HOLD_CLOSE_TRIGGER,
    ManageMaxHoldCloseBridgeError,
    adapt_manage_max_hold_to_dec_close,
)
from tests.harness.execpos_scenarios import feed_opened_position
from vfoundation.core.protocol import Message


@pytest.fixture
def mock_clock() -> MockClock:
    clock = MockClock(start_ms=1_000_000)
    set_clock(clock)
    yield clock
    reset_clock()


def test_manage_max_hold_bridge_emits_typed_non_cmd_dec_close() -> None:
    msg = Message(
        op="UPD",
        verb="MARKET_DATA",
        src="ws",
        dst="exec",
        rid="rid-max-hold-typed",
        pld={"symbol": "BTCUSDT", "last_price": "50000"},
        data_ref=["obs://upstream/manage_tick"],
    )

    intake, emission, decision = adapt_manage_max_hold_to_dec_close(
        msg,
        symbol="BTCUSDT",
        side="SELL",
        qty=Decimal("1.25"),
        elapsed_sec=61.9,
        max_hold_sec=60,
        position_open_ts=1000.0,
    )

    assert intake.symbol == "BTCUSDT"
    assert emission.trigger == MANAGE_MAX_HOLD_CLOSE_TRIGGER
    assert emission.idempotent_key == "manage_max_hold:BTCUSDT:1000000:1.25:60"
    assert decision.verb == "CLOSE"
    assert decision.why == "max_hold_timeout_61s_reduce_only"
    assert decision.pld["reduce_only"] is True
    assert decision.pld["side"] == "SELL"
    assert decision.pld["qty"] == "1.25"
    assert decision.pld["reason"] == "MAX_HOLD_TIME_EXCEEDED"
    assert decision.pld["trigger"] == MANAGE_MAX_HOLD_CLOSE_TRIGGER
    assert decision.pld["idempotent_key"] == emission.idempotent_key
    assert any(
        f"contract={MANAGE_MAX_HOLD_CLOSE_CONTRACT}" in ref
        for ref in (decision.data_ref or [])
    )


def test_manage_max_hold_bridge_rejects_malformed_runtime_state() -> None:
    msg = Message(
        op="UPD",
        verb="MARKET_DATA",
        src="ws",
        dst="exec",
        rid="rid-bad-max-hold",
        pld={"symbol": "BTCUSDT"},
    )

    with pytest.raises(ManageMaxHoldCloseBridgeError):
        adapt_manage_max_hold_to_dec_close(
            msg,
            symbol="BTCUSDT",
            side="SELL",
            qty=Decimal("0"),
            elapsed_sec=61,
            max_hold_sec=60,
            position_open_ts=1000.0,
        )


def test_manage_handle_emits_typed_max_hold_close_without_raw_inline_fields(
    fsm_harness,
    mock_clock: MockClock,
) -> None:
    fsm, _bus, _cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    manage.position_open_ts = mock_clock.now_sec()

    with patch.object(manage, "_get_max_hold_sec", return_value=1):
        mock_clock.set_time_ms(1_002_000)
        msg = Message(
            op="UPD",
            verb="MARKET_DATA",
            src="ws",
            dst="exec",
            rid="rid-manage-max-hold",
            pld={"symbol": "BTCUSDT", "last_price": "50000", "ts": 1_002_000},
        )
        res = manage.handle(msg)

    assert res is not None
    assert res.op == "DEC"
    assert res.verb == "CLOSE"
    assert res.why == "max_hold_timeout_2s_reduce_only"
    assert res.pld["symbol"] == "BTCUSDT"
    assert res.pld["side"] == "SELL"
    assert res.pld["qty"] == "1.0"
    assert res.pld["reduce_only"] is True
    assert res.pld["reason"] == "MAX_HOLD_TIME_EXCEEDED"
    assert res.pld["trigger"] == MANAGE_MAX_HOLD_CLOSE_TRIGGER
    assert res.pld["idempotent_key"] == "manage_max_hold:BTCUSDT:1000000:1.0:1"
    assert any(
        f"contract={MANAGE_MAX_HOLD_CLOSE_CONTRACT}" in ref
        for ref in (res.data_ref or [])
    )


def test_manage_max_hold_dec_close_executes_downstream_package5_submission(
    fsm_harness,
    mock_clock: MockClock,
) -> None:
    fsm, _bus, cfg = fsm_harness
    cfg.get_domain_mode.return_value = "testnet"  # type: ignore[attr-defined]

    adapter = AsyncMock()
    adapter.base_url = "https://testnet.binancefuture.com"
    adapter.get_open_positions.return_value = [{"symbol": "BTCUSDT", "positionAmt": "1.0"}]
    adapter.get_open_orders.return_value = []

    fsm.adapter = adapter
    fsm.shadow_mode = False

    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    manage.position_open_ts = mock_clock.now_sec()

    with patch.object(manage, "_get_max_hold_sec", return_value=1):
        mock_clock.set_time_ms(1_002_000)
        decision = manage.handle(
            Message(
                op="UPD",
                verb="MARKET_DATA",
                src="ws",
                dst="exec",
                rid="rid-max-hold-live",
                pld={"symbol": "BTCUSDT", "last_price": "50000", "ts": 1_002_000},
            )
        )

    assert decision is not None
    assert decision.pld["trigger"] == MANAGE_MAX_HOLD_CLOSE_TRIGGER

    async def _run() -> None:
        fsm_sleep = AsyncMock()
        import apps.reference.domains.execution_position.fsm as fsm_mod

        orig_sleep = fsm_mod.asyncio.sleep
        fsm_mod.asyncio.sleep = fsm_sleep
        try:
            await fsm._execute_decision(decision)
        finally:
            fsm_mod.asyncio.sleep = orig_sleep

    asyncio.run(_run())

    adapter.place_market_reduce_only.assert_awaited_once()
    args, kwargs = adapter.place_market_reduce_only.await_args
    assert args[0] == "BTCUSDT"
    assert args[1] == "SELL"
    assert args[2] == "1.0"
    assert "new_client_order_id" in kwargs


def test_explicit_close_producer_bridge_remains_unchanged() -> None:
    flow = CloseFlowFSM()
    decision = flow.handle(
        Message(
            op="CMD",
            verb="CLOSE",
            src="decision_making",
            dst="execution_position",
            rid="rid-explicit-close",
            pld={
                "symbol": "BTCUSDT",
                "reason": "MANUAL_CLOSE",
                "idempotent_key": "explicit-close-1",
            },
        )
    )

    assert decision is not None
    assert decision.pld["trigger"] == "CMD:CLOSE"
    assert decision.pld["idempotent_key"] == "explicit-close-1"
    assert decision.pld["reason"] == "MANUAL_CLOSE"
    assert not any(
        f"contract={MANAGE_MAX_HOLD_CLOSE_CONTRACT}" in ref
        for ref in (decision.data_ref or [])
    )
    assert any(
        f"contract={CLOSE_PRODUCER_BRIDGE_CONTRACT}" in ref
        for ref in (decision.data_ref or [])
    )


def test_manage_max_hold_bypasses_cmd_close_producer_adapter(
    fsm_harness,
    mock_clock: MockClock,
) -> None:
    fsm, _bus, _cfg = fsm_harness
    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    manage.position_open_ts = mock_clock.now_sec()

    with patch.object(manage, "_get_max_hold_sec", return_value=1), patch(
        "apps.reference.domains.execution_position.fsm_close.adapt_cmd_close_to_dec_close"
    ) as producer_adapter:
        mock_clock.set_time_ms(1_002_000)
        result = manage.handle(
            Message(
                op="UPD",
                verb="MARKET_DATA",
                src="ws",
                dst="exec",
                rid="rid-max-hold-bypass",
                pld={"symbol": "BTCUSDT", "last_price": "50000", "ts": 1_002_000},
            )
        )

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "CLOSE"
    assert result.pld["trigger"] == MANAGE_MAX_HOLD_CLOSE_TRIGGER
    producer_adapter.assert_not_called()
