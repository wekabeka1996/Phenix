"""Tests for watchdog-driven EVT:TRADE_EXECUTED delivery (OCO-11.6)."""

from __future__ import annotations

import logging
from typing import Dict, List

import pytest
from vfoundation.core.fsm_emit_compat import Message

import apps.reference.domains.execution_position.fsm as execpos_mod
from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog


@pytest.fixture(autouse=True)
def _mute_background_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable background cleanup scheduling to avoid stray tasks in tests."""

    monkeypatch.setattr(
        execpos_mod.ExecPosFSM,
        "_schedule_fsm_cleanup_loop",
        lambda self: None,
    )
    monkeypatch.setattr(
        execpos_mod.ExecPosFSM,
        "_schedule_guardian_start",
        lambda self: None,
    )


@pytest.mark.asyncio
async def test_watchdog_emit_flows_through_manage_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure REST-detected fills reach ManageFlow via ExecPosFSM.emit helper."""

    captured: List[Message] = []

    class CaptureManageFlow:
        def __init__(self, *_, **__):
            self.state = "FLAT"
            self._auto_manage_enabled = True
            self.position_qty = 0
            self.position_open_ts = 0.0

        def handle(self, msg: Message):
            captured.append(msg)
            return None

    monkeypatch.setattr(execpos_mod, "ManageFlowFSM", CaptureManageFlow)

    fsm = execpos_mod.ExecPosFSM(config={}, fsm=None, shadow_mode=True)
    fsm.correlation_store.put_entry_ack(
        "rest-fill-1",
        {
            "corr_id": "corr-123",
            "oco_group_id": "oco-1",
            "rid": "rid-123",
            "parent_client_order_id": "PARENT-1",
        },
    )

    payload = {
        "symbol": "SOLUSDT",
        "quantity": "1.0",
        "side": "BUY",
        "orderId": "rest-fill-1",
    }

    await fsm._emit_watchdog_event("EVT:TRADE_EXECUTED", payload)

    assert captured, "ManageFlow must receive TRADE_EXECUTED emitted via watchdog"
    assert captured[0].verb == "TRADE_EXECUTED"
    assert captured[0].pld.get("symbol") == "SOLUSDT"
    assert captured[0].pld.get("corr_id") == "corr-123"
    assert captured[0].pld.get("clientOrderId") == "PARENT-1"
    assert captured[0].rid == "rid-123"
    assert captured[0].pld.get("domain") == "execution_position"


@pytest.mark.asyncio
async def test_watchdog_emit_calls_handle_with_fsm_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    """Watchdog emitting via FSM bus must still trigger direct handle for ManageFlow."""

    captured: List[Message] = []

    class CaptureManageFlow:
        def __init__(self, *_, **__):
            self.state = "FLAT"
            self._auto_manage_enabled = True
            self.position_qty = 0
            self.position_open_ts = 0.0

        def handle(self, msg: Message):
            captured.append(msg)
            return None

    class FakeBus:
        def __init__(self):
            self._listeners: dict[str, list] = {}
            self.emitted: list[str] = []

        def listen(self, event: str, callback):
            self._listeners.setdefault(event, []).append(callback)

        def emit(self, message: Message):
            if not isinstance(message, Message):
                raise TypeError("FakeBus expects Message signature")
            event = f"EVT:{message.verb}" if message.verb else message.verb
            self.emitted.append(event)
            for callback in self._listeners.get(event, []):
                callback(message)

    monkeypatch.setattr(execpos_mod, "ManageFlowFSM", CaptureManageFlow)

    bus = FakeBus()
    fsm = execpos_mod.ExecPosFSM(config={}, fsm=bus, shadow_mode=True)

    payload = {
        "symbol": "SOLUSDT",
        "quantity": "2.5",
        "side": "BUY",
        "orderId": "rest-fill-2",
    }

    await fsm._emit_watchdog_event("EVT:TRADE_EXECUTED", payload)

    assert captured, "ManageFlow should handle watchdog fill even when bus emit succeeds"
    assert "EVT:TRADE_EXECUTED" in bus.emitted


@pytest.mark.asyncio
async def test_watchdog_emit_invokes_on_trade_executed(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Watchdog emissions must reach ExecPosFSM._on_trade_executed via handle path."""

    captured: Dict[str, Message] = {}

    def fake_on_trade_executed(self, msg: Message) -> None:  # noqa: D401
        captured["msg"] = msg

    monkeypatch.setattr(
        execpos_mod.ExecPosFSM,
        "_on_trade_executed",
        fake_on_trade_executed,
        raising=False,
    )

    fsm = execpos_mod.ExecPosFSM(config={}, fsm=None, shadow_mode=True)

    payload = {
        "symbol": "SOLUSDT",
        "quantity": "3.0",
        "side": "BUY",
        "price": "105.0",
        "orderId": "rest-fill-3",
    }

    caplog.set_level(logging.INFO)
    await fsm._emit_watchdog_event("EVT:TRADE_EXECUTED", payload)

    assert captured.get("msg"), "_on_trade_executed must be invoked"
    assert captured["msg"].pld.get("symbol") == "SOLUSDT"
    assert any(
        record.message == "WATCHDOG_EVENT_DELIVERED_TO_FSM" for record in caplog.records
    ), "Delivery log must be emitted"


@pytest.mark.asyncio
async def test_watchdog_logs_when_emit_fn_missing(caplog: pytest.LogCaptureFixture) -> None:
    """Watchdog must log an error when emit_fn is not bound."""

    watchdog = OrderTimeoutWatchdog()
    caplog.set_level(logging.ERROR)

    await watchdog._emit_via_hook(
        event_name="EVT:TRADE_EXECUTED",
        payload={
            "symbol": "SOLUSDT",
            "orderId": "missing-hook",
            "quantity": "1.0",
        },
        log_event="WATCHDOG_EMIT_TRADE_EXECUTED",
    )

    assert any(
        record.message == "WATCHDOG_EMIT_MISSING" for record in caplog.records
    ), "Missing emit_fn should be logged as WATCHDOG_EMIT_MISSING"
