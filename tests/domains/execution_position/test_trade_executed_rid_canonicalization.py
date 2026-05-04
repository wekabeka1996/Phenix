from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.orchestration.event_handlers import EPEventHandlers
from apps.reference.domains.execution_position.fsm import (
    _build_watchdog_trade_executed_message,
)
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.schema_registry import init_global_registry
from vfoundation.dr import wal


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _runtime_config(tmp_path: Path):
    config = ConfigLoader().load_config()
    shadow_path = tmp_path / "shadow_journal.jsonl"
    config.observability.shadow_journal.enabled = True
    config.observability.shadow_journal.path = str(shadow_path)
    config.observability.shadow_journal.schema_version = "1.0.0"
    config.observability.shadow_journal.instrumentation_version = "1.0.0"
    config.observability.shadow_journal.critical_events = list(
        DEFAULT_CRITICAL_EVENTS)
    return config, shadow_path


def test_watchdog_trade_executed_message_uses_payload_rid_as_envelope_rid() -> None:
    payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "quantity": "0.01",
        "price": "100.0",
        "status": "FILLED",
        "orderId": "order-123",
        "exchangeOrderId": "order-123",
        "clientOrderId": "client-123",
        "client_order_id": "client-123",
        "rid": "RID-123",
        "ts": 1710000000000,
        "ts_ms": 1710000000000,
        "venue": "binance",
    }

    msg = _build_watchdog_trade_executed_message(
        "EVT:TRADE_EXECUTED",
        payload,
        why="polling_fill",
    )

    assert msg.op == "EVT"
    assert msg.verb == "TRADE_EXECUTED"
    assert msg.rid == "RID-123"
    assert msg.pld["rid"] == "RID-123"
    assert msg.pld["orderId"] == "order-123"
    assert msg.pld["clientOrderId"] == "client-123"


def test_trade_executed_canonical_rid_queries_wal_shadow_and_lifecycle(tmp_path) -> None:
    init_global_registry(project_root=".")
    original_wal_dir = wal.WAL_DIR
    wal_dir = tmp_path / "wal"
    wal.set_wal_dir(wal_dir)

    try:
        config, shadow_path = _runtime_config(tmp_path)
        bus = FSMCore()
        attach_shadow_journal(bus, config)
        with patch(
            "apps.reference.domains.position_tracking.position_tracking.attach_execution_truth_hardening",
            return_value=None,
        ):
            PositionTracking(bus, config)

        lifecycle_path = tmp_path / "trade_lifecycle.jsonl"
        lifecycle = TradeLifecycleLogger(
            log_file=str(lifecycle_path),
            orphan_ttl_sec=3600,
        )
        lifecycle.on_intent(
            rid="RID-123",
            symbol="BTCUSDT",
            side="buy",
            strategy_id="aurora",
            entry_type="MARKET",
        )
        lifecycle.on_order_placed(
            rid="RID-123",
            order_id="order-123",
            price=100.0,
        )

        fake_fsm = SimpleNamespace(
            _last_lifecycle_rid_by_symbol={},
            _last_lifecycle_fill_price_by_symbol={},
        )
        handlers = EPEventHandlers(fake_fsm)
        bus.listen("EVT:TRADE_EXECUTED", handlers.on_trade_executed)

        payload = {
            "symbol": "BTCUSDT",
            "side": "buy",
            "quantity": "0.01",
            "price": "100.0",
            "status": "FILLED",
            "orderId": "order-123",
            "exchangeOrderId": "order-123",
            "clientOrderId": "client-123",
            "client_order_id": "client-123",
            "rid": "RID-123",
            "ts": 1710000000000,
            "ts_ms": 1710000000000,
            "venue": "binance",
        }
        msg = _build_watchdog_trade_executed_message(
            "EVT:TRADE_EXECUTED",
            payload,
            why="polling_fill",
        )

        with patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
            lifecycle,
        ):
            bus.emit(msg)

        lifecycle.on_close(
            rid="RID-123",
            close_price=100.0,
            close_reason="POSITION_CLOSED_DETECTED",
        )

        wal_events, why_chain, integrity_ok = wal.read_by_rid("RID-123")
        assert integrity_ok is True
        assert len(wal_events) == 1
        wal_record = wal_events[0]
        assert wal_record["rid"] == "RID-123"
        assert wal_record["pld"]["rid"] == "RID-123"
        assert wal_record["verb"] == "TRADE_EXECUTED"

        shadow_rows = _read_jsonl(shadow_path)
        shadow_fill_rows = [
            row for row in shadow_rows if row["event_name"] == "EVT:TRADE_EXECUTED"
        ]
        assert shadow_fill_rows
        shadow_row = shadow_fill_rows[0]
        assert shadow_row["rid"] == "RID-123"
        assert shadow_row["order_id"] == "order-123"
        assert shadow_row["payload_fragment"]["orderId"] == "order-123"

        lifecycle_rows = _read_jsonl(lifecycle_path)
        assert len(lifecycle_rows) == 3

        ordered_row = lifecycle_rows[0]
        assert ordered_row["record_kind"] == "trade_lifecycle_snapshot"
        assert ordered_row["event_type"] == "TRADE_LIFECYCLE_ORDERED"
        assert ordered_row["status"] == "ORDERED"
        assert ordered_row["order_id"] == "order-123"

        filled_row = lifecycle_rows[1]
        assert filled_row["record_kind"] == "trade_lifecycle_snapshot"
        assert filled_row["event_type"] == "TRADE_LIFECYCLE_FILLED"
        assert filled_row["status"] == "FILLED"
        assert filled_row["order_id"] == "order-123"
        assert float(filled_row["fill_price"]) == 100.0

        lifecycle_row = lifecycle_rows[2]
        assert lifecycle_row["rid"] == "RID-123"
        assert lifecycle_row["status"] == "CLOSED"
        assert lifecycle_row["order_id"] == "order-123"

        assert why_chain == []
    finally:
        wal.set_wal_dir(original_wal_dir)
