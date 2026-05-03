from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from jsonschema import validate

from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
from apps.reference.domains.execution_position.state.order_index import OrderIndex
from apps.reference.domains.execution_position.adapters.watchdog import OrderTimeoutWatchdog
from vfoundation.core.fsm_core import FSMCore, InvalidMessagePayloadError
from vfoundation.core.schema_registry import init_global_registry


@pytest.fixture(autouse=True)
def _reset_global_registry():
    import vfoundation.core.schema_registry as mod

    original = mod._global_registry
    mod._global_registry = None
    try:
        yield
    finally:
        mod._global_registry = original


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _trade_executed_schema() -> dict:
    schema_path = (
        _repo_root()
        / "apps"
        / "reference"
        / "domains"
        / "position_tracking"
        / "schemas"
        / "trade_executed_v1.json"
    )
    return json.loads(schema_path.read_text(encoding="utf-8"))


class _CapturingFSMCore:
    def __init__(self, order_index=None):
        self.order_index = order_index
        self.emitted: list[tuple[str, dict, str]] = []

    def emit(self, event_name: str, payload: dict, why: str) -> None:
        self.emitted.append((event_name, payload, why))


def test_ws_entry_fill_payload_includes_side_and_matches_schema() -> None:
    idx = OrderIndex(ttl_sec=600)
    idx.upsert_from_open(
        rid="rid-entry-1",
        idempotent_key="idem-entry-1",
        clientOrderId="ENTRY-BTCUSDT-1",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
    )
    idx.attach_exchange_id(
        clientOrderId="ENTRY-BTCUSDT-1",
        exchangeOrderId="7001",
    )

    fsm_core = _CapturingFSMCore(order_index=idx)
    client = BinanceWebSocketClient(
        api_key="k",
        base_url="http://example.invalid",
        use_testnet=True,
        fsm_core=fsm_core,
    )

    client._handle_ws_message(
        {
            "e": "ORDER_TRADE_UPDATE",
            "T": 1710000000123,
            "o": {
                "c": "ENTRY-BTCUSDT-1",
                "i": "7001",
                "X": "FILLED",
                "s": "BTCUSDT",
                "z": "0.01",
                "l": "0.01",
                "S": "BUY",
                "o": "MARKET",
                "q": "0.01",
                "ap": "50000.0",
                "p": "50000.0",
            },
        }
    )

    assert len(fsm_core.emitted) == 1
    event_name, payload, why = fsm_core.emitted[0]
    assert event_name == "EVT:TRADE_EXECUTED"
    assert why == "WS_ORDER_UPDATE_FILLED"
    assert payload["side"] == "buy"
    validate(instance=payload, schema=_trade_executed_schema())


def test_ws_close_fill_payload_includes_side_and_matches_schema() -> None:
    idx = OrderIndex(ttl_sec=600)
    idx.register_bracket_child(
        rid="rid-close-1",
        idempotent_key="idem-close-1",
        clientOrderId="SL-BTCUSDT-1",
        exchangeOrderId="7002",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        order_kind="SL",
    )

    fsm_core = _CapturingFSMCore(order_index=idx)
    client = BinanceWebSocketClient(
        api_key="k",
        base_url="http://example.invalid",
        use_testnet=True,
        fsm_core=fsm_core,
    )

    client._handle_ws_message(
        {
            "e": "ORDER_TRADE_UPDATE",
            "T": 1710000000456,
            "o": {
                "c": "SL-BTCUSDT-1",
                "i": "7002",
                "X": "FILLED",
                "s": "BTCUSDT",
                "z": "0.01",
                "l": "0.01",
                "S": "SELL",
                "o": "STOP_MARKET",
                "q": "0.01",
                "ap": "49900.0",
                "p": "49900.0",
            },
        }
    )

    assert len(fsm_core.emitted) == 1
    event_name, payload, why = fsm_core.emitted[0]
    assert event_name == "EVT:TRADE_EXECUTED"
    assert why == "WS_ORDER_UPDATE_FILLED"
    assert payload["side"] == "sell"
    assert payload["close_reason"] == "SL"
    assert payload["bracket_role"] == "SL"
    validate(instance=payload, schema=_trade_executed_schema())


async def test_watchdog_recovered_fill_derives_side_from_tracked_deadline() -> None:
    emitted: list[tuple[str, dict]] = []

    async def emit_fn(event_name: str, payload: dict) -> None:
        emitted.append((event_name, payload))

    watchdog = OrderTimeoutWatchdog(
        config={"ack_ttl_ms": 1000, "fill_ttl_ms": 5000, "check_interval_ms": 1000}
    )
    watchdog.set_hooks(
        get_order_fn=AsyncMock(
            return_value={
                "status": "FILLED",
                "executedQty": "0.01",
                "avgPrice": "50000.0",
                "clientOrderId": "ENTRY-BTCUSDT-WD",
            }
        ),
        emit_fn=emit_fn,
    )
    watchdog.track_order_placed(
        "ord-1",
        "ENTRY-BTCUSDT-WD",
        "BTCUSDT",
        rid="rid-wd-1",
        side="BUY",
    )
    watchdog.on_order_ack("ord-1")

    await watchdog._poll_order_statuses()

    assert len(emitted) == 1
    event_name, payload = emitted[0]
    assert event_name == "EVT:TRADE_EXECUTED"
    assert payload["side"] == "buy"
    validate(instance=payload, schema=_trade_executed_schema())


def test_fsmcore_rejects_trade_executed_without_side_when_not_derivable() -> None:
    init_global_registry(project_root=".")
    bus = FSMCore()

    with pytest.raises(InvalidMessagePayloadError, match="side"):
        bus.emit(
            "EVT:TRADE_EXECUTED",
            {
                "symbol": "BTCUSDT",
                "price": "50000.0",
                "quantity": "0.01",
                "orderId": "12345",
                "clientOrderId": "ENTRY-BTCUSDT-MANUAL",
            },
            "manual_test_emit",
            rid="rid-missing-side",
        )