from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from vfoundation.core.fsm_emit_compat import Message

from apps.reference.domains.execution_position.flows.open.intent_router import (
    IntentRouter,
)


class _Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, str]] = []

    def emit(self, event_name: str, payload: dict, why: str = "", data_ref=None, **kwargs) -> None:
        self.events.append((event_name, payload, why))


def test_external_close_maps_to_cmd_close_when_lifecycle_is_active() -> None:
    fsm = MagicMock()
    fsm.bus = _Bus()
    fsm.manage_flows = {
        "BNBUSDT": SimpleNamespace(
            has_active_lifecycle=lambda: True,
            position_qty=Decimal("1.5"),
        )
    }
    fsm._last_lifecycle_ikey_by_symbol = {"BNBUSDT": "life-1"}
    result = SimpleNamespace(op="DEC", verb="CLOSE", pld={"symbol": "BNBUSDT"}, why="ok", data_ref=None, rid="rid-1")
    fsm.handle.return_value = result

    router = IntentRouter(fsm)
    msg = Message(
        op="CMD",
        verb="EXTERNAL_POSITION_CLOSE_REQUEST_V1",
        src="shadow_telemetry",
        dst="execution_position",
        rid="rid-1",
        pld={
            "action_id": "action-1",
            "lifecycle_id": "life-1",
            "symbol": "BNBUSDT",
            "reason": "model close",
            "source": "external_llm",
            "idempotent_key": "idem-1",
        },
        why="test",
    )

    router.on_external_position_close_request(msg)

    fsm.handle.assert_called_once()
    cmd_close = fsm.handle.call_args[0][0]
    assert cmd_close.verb == "CLOSE"
    assert cmd_close.pld["close_guard_prevalidated"] is True
    assert cmd_close.pld["lifecycle_id"] == "life-1"


def test_external_close_rejects_lifecycle_mismatch() -> None:
    fsm = MagicMock()
    fsm.bus = _Bus()
    fsm.manage_flows = {"BNBUSDT": SimpleNamespace(has_active_lifecycle=lambda: True)}
    fsm._last_lifecycle_ikey_by_symbol = {"BNBUSDT": "life-live"}
    router = IntentRouter(fsm)
    msg = Message(
        op="CMD",
        verb="EXTERNAL_POSITION_CLOSE_REQUEST_V1",
        src="shadow_telemetry",
        dst="execution_position",
        rid="rid-2",
        pld={
            "action_id": "action-2",
            "lifecycle_id": "life-other",
            "symbol": "BNBUSDT",
            "reason": "model close",
            "source": "external_llm",
            "idempotent_key": "idem-2",
        },
        why="test",
    )

    router.on_external_position_close_request(msg)

    assert any(event[0] == "EVT:LLM_CLOSE_REJECTED_V1" for event in fsm.bus.events)
    fsm.handle.assert_not_called()


def test_external_bracket_amend_replaces_live_brackets() -> None:
    loop = asyncio.new_event_loop()
    try:
        manage_flow = SimpleNamespace(
            has_active_lifecycle=lambda: True,
            position_qty=Decimal("2"),
            entry_order_id="entry-1",
            entry_client_order_id="cid-1",
            position_side="BUY",
            position_entry_price=Decimal("100.0"),
        )
        fsm = MagicMock()
        fsm.bus = _Bus()
        fsm.manage_flows = {"BNBUSDT": manage_flow}
        fsm._last_lifecycle_ikey_by_symbol = {"BNBUSDT": "life-3"}
        fsm._get_async_loop.return_value = loop
        fsm._submit_async.side_effect = lambda coro, _loop: _loop.run_until_complete(coro)
        fsm.config = SimpleNamespace(instruments={"BNBUSDT": SimpleNamespace(tick_size=Decimal("0.1"))})
        fsm.order_guardian = SimpleNamespace(cleanup_orphans=AsyncMock())
        fsm._bracket_mgr = SimpleNamespace(place_brackets_parallel=AsyncMock())

        router = IntentRouter(fsm)
        msg = Message(
            op="CMD",
            verb="EXTERNAL_BRACKET_AMEND_REQUEST_V1",
            src="shadow_telemetry",
            dst="execution_position",
            rid="rid-3",
            pld={
                "action_id": "action-3",
                "lifecycle_id": "life-3",
                "symbol": "BNBUSDT",
                "side": "BUY",
                "entry_price": "100.0",
                "tp_price": "103.0",
                "sl_price": "99.0",
                "reason": "adjust brackets",
                "source": "external_llm",
                "idempotent_key": "idem-3",
            },
            why="test",
        )

        router.on_external_bracket_amend_request(msg)

        fsm.order_guardian.cleanup_orphans.assert_awaited_once()
        fsm._bracket_mgr.place_brackets_parallel.assert_awaited_once()
    finally:
        loop.close()
