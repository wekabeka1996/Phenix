from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.contract_layer.trade_intent_reject_contracts import (
    emit_canonical_trade_intent_rejected_event,
)
from apps.reference.domains.execution_position.orchestration.event_handlers import EPEventHandlers
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.schema_registry import init_global_registry


def _shadow_cfg(path: Path):
    return SimpleNamespace(
        observability=SimpleNamespace(
            shadow_journal=SimpleNamespace(
                enabled=True,
                path=str(path),
                schema_version="1.0.0",
                instrumentation_version="1.0.0",
                critical_events=list(DEFAULT_CRITICAL_EVENTS),
            )
        )
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_fsmcore_normalizes_trade_executed_payload_to_schema_valid_runtime_shape() -> None:
    init_global_registry(project_root=".")
    bus = FSMCore()

    seen: list[dict] = []
    bus.listen("EVT:TRADE_EXECUTED",
               lambda msg: seen.append(dict(msg.pld or {})))

    bus.emit(
        "EVT:TRADE_EXECUTED",
        {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "price": "2176.61",
            "last_fill_qty": "0.01",
            "orderId": "8617505424",
            "clientOrderId": "ENTRY-7f9aee0fba07",
            "status": "FILLED",
            "ts_ms": 1774428909509,
            "rid": "aurora_ETHUSDT_1774428903370",
        },
        "WS_ORDER_UPDATE_FILLED",
        rid="aurora_ETHUSDT_1774428903370",
    )

    assert len(seen) == 1
    payload = seen[0]
    assert payload["quantity"] == "0.01"
    assert payload["ts"] == 1774428909509
    assert payload["ts_ms"] == 1774428909509
    assert payload["venue"] == "binance"
    assert payload["side"] == "sell"
    assert payload["orderId"] == "8617505424"


def test_raced_boundary_reject_chain_converges_to_closed_lifecycle_without_orphan_ttl(tmp_path) -> None:
    init_global_registry(project_root=".")
    journal_path = tmp_path / "shadow_journal.jsonl"
    lifecycle_path = tmp_path / "trade_lifecycle.jsonl"

    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    config = ConfigLoader().load_config()
    config.observability.shadow_journal.enabled = True
    config.observability.shadow_journal.path = str(journal_path)
    config.observability.shadow_journal.critical_events = list(
        DEFAULT_CRITICAL_EVENTS)
    PositionTracking(bus, config)

    # Disable execution truth hardening AFTER PositionTracking (which attaches
    # it from the terminal identity cache on disk).  Without this, a stale
    # cache hit can suppress EVT:TRADE_EXECUTED causing a non-deterministic
    # lifecycle row count.
    bus._execution_truth_hardening = None

    lifecycle = TradeLifecycleLogger(
        log_file=str(lifecycle_path), orphan_ttl_sec=3600)
    lifecycle.on_intent(
        rid="aurora_ETHUSDT_1774428903370",
        symbol="ETHUSDT",
        side="SELL",
        strategy_id="aurora",
        entry_type="LIMIT",
    )

    fake_fsm = MagicMock()
    fake_fsm._last_lifecycle_rid_by_symbol = {}
    fake_fsm._last_lifecycle_fill_price_by_symbol = {}
    handlers = EPEventHandlers(fake_fsm)
    bus.listen("EVT:TRADE_EXECUTED", handlers.on_trade_executed)

    with patch("apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle", lifecycle):
        emit_canonical_trade_intent_rejected_event(
            fsm=bus,
            payload={
                "ts_ms": int(time.time() * 1000),
                "symbol": "ETHUSDT",
                "reason_code": "NRR-EXECUTION-NO-DOWNSTREAM-EVENT",
                "stage": "EXECUTION",
                "why": "trade_intent_boundary_audit:no_downstream_event",
                "rid": "aurora_ETHUSDT_1774428903370",
            },
            rid="aurora_ETHUSDT_1774428903370",
            src="execution_position",
            why="trade_intent_boundary_audit:no_downstream_event",
            lifecycle=lifecycle,
            fallback_symbol="ETHUSDT",
            fallback_reason_code="NRR-EXECUTION-NO-DOWNSTREAM-EVENT",
            fallback_stage="EXECUTION",
            fallback_why="trade_intent_boundary_audit:no_downstream_event",
        )
        lifecycle.on_order_placed(
            rid="aurora_ETHUSDT_1774428903370",
            order_id="8617505424",
            price=2176.61,
        )
        bus.emit(
            "EVT:TRADE_EXECUTED",
            {
                "symbol": "ETHUSDT",
                "side": "SELL",
                "price": "2176.61",
                "last_fill_qty": "0.01",
                "orderId": "8617505424",
                "clientOrderId": "ENTRY-7f9aee0fba07",
                "status": "FILLED",
                "ts_ms": 1774428909509,
                "rid": "aurora_ETHUSDT_1774428903370",
            },
            "WS_ORDER_UPDATE_FILLED",
            rid="aurora_ETHUSDT_1774428903370",
        )
        lifecycle.on_close(
            rid="aurora_ETHUSDT_1774428903370",
            close_price=2175.10,
            close_reason="POSITION_CLOSED_DETECTED",
        )

    lifecycle_rows = _read_jsonl(lifecycle_path)
    # Full race-recovery lifecycle: REJECTED → ORDERED (reconciled) → FILLED → CLOSED
    # The FILLED row is produced by on_trade_executed calling lifecycle.on_fill().
    assert len(lifecycle_rows) == 4
    assert lifecycle_rows[0]["status"] == "REJECTED"
    assert lifecycle_rows[1]["event_type"] == "TRADE_LIFECYCLE_ORDERED"
    assert lifecycle_rows[1]["status"] == "ORDERED"
    assert lifecycle_rows[1]["order_id"] == "8617505424"
    assert lifecycle_rows[2]["event_type"] == "TRADE_LIFECYCLE_FILLED"
    assert lifecycle_rows[2]["status"] == "FILLED"
    assert lifecycle_rows[2]["fill_price"] == 2176.61
    assert lifecycle_rows[2]["fill_qty"] == 0.01
    assert lifecycle_rows[3]["status"] == "CLOSED"
    assert lifecycle_rows[3]["prior_terminal_status"] == "REJECTED"
    assert lifecycle_rows[3]["reconciliation_source"] == "order_placed"
    assert not any(row["status"] == "ORPHANED_TTL" for row in lifecycle_rows)

    shadow_rows = _read_jsonl(journal_path)
    reject_events = [r for r in shadow_rows if r["event_name"]
                     == "EVT:TRADE_INTENT_REJECTED"]
    fill_events = [r for r in shadow_rows if r["event_name"]
                   == "EVT:TRADE_EXECUTED"]
    assert len(reject_events) == 1
    assert len(fill_events) >= 1
    assert "reason" not in reject_events[0]["payload_fragment"]
    assert fill_events[0]["payload_fragment"]["orderId"] == "8617505424"
