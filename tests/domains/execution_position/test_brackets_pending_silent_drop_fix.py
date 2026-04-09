import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.reference.domains.execution_position.fsm_manage import (
    ManageFlowFSM,
    ManageState,
)
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message
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
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _pending_tp_fill_message(symbol: str = "BTCUSDT") -> Message:
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="rid-pending-tp-fill",
        why="test_pending_tp_fill",
        pld={
            "symbol": symbol,
            "orderId": "tp-order",
            "clientOrderId": "TP-test",
            "client_order_id": "TP-test",
            "side": "SELL",
            "qty": "0.10",
            "quantity": "0.10",
            "price": "1010",
            "order_type": "TAKE_PROFIT_MARKET",
            "reduceOnly": True,
        },
    )


def _entry_like_fill_message(symbol: str = "BTCUSDT") -> Message:
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="rid-second-entry",
        why="test_second_entry",
        pld={
            "symbol": symbol,
            "orderId": "entry-order-2",
            "clientOrderId": "ENTRY-SECOND",
            "client_order_id": "ENTRY-SECOND",
            "side": "BUY",
            "qty": "0.20",
            "quantity": "0.20",
            "price": "990",
        },
    )


def _prime_pending_manage_flow(manage: ManageFlowFSM, *, symbol: str = "BTCUSDT") -> None:
    manage.state = ManageState.BRACKETS_PENDING
    manage.symbol = symbol
    manage.position_qty = Decimal("0.10")
    manage.position_entry_price = Decimal("1000")
    manage.position_side = "BUY"
    manage.position_open_ts = 1.0
    manage.entry_order_id = "entry-order"
    manage.entry_client_order_id = "ENTRY-1"
    manage.sl_order_id = "sl-order"
    manage.tp_order_id = "tp-order"
    manage.sl_algo_client_id = "algo-sl-1"
    manage.tp_algo_client_id = "algo-tp-1"


@pytest.fixture(autouse=True)
def _init_schema_registry():
    import vfoundation.core.schema_registry as mod

    original = mod._global_registry
    init_global_registry(
        project_root=".",
        yaml_path="apps/reference/dictionaries/verb_registry_v1.yaml",
    )
    yield
    mod._global_registry = original


def test_brackets_pending_trade_executed_tp_fill_is_not_silently_dropped(fsm_config):
    manage = ManageFlowFSM(config=fsm_config)
    observed: list[tuple[str, dict]] = []
    manage.set_observability_hook(lambda topic, payload: observed.append((topic, dict(payload))))
    _prime_pending_manage_flow(manage)

    result = manage.handle(_pending_tp_fill_message())

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "CANCEL_ORDER"
    assert result.pld["orderId"] == "sl-order"
    assert manage.state == ManageState.FLAT
    assert manage.has_active_lifecycle() is False
    exit_match = next(payload for topic, payload in observed if topic == "EVT:EXIT_MATCH_ATTEMPTED")
    assert exit_match["matched"] is True
    assert exit_match["inferred_role"] == "TP"
    assert exit_match["local_state_before"] == ManageState.BRACKETS_PENDING.value
    assert exit_match["local_state_after"] == ManageState.FLAT.value


def test_brackets_pending_entry_like_fill_still_guard_blocks(fsm_config):
    manage = ManageFlowFSM(config=fsm_config)
    observed: list[tuple[str, dict]] = []
    manage.set_observability_hook(lambda topic, payload: observed.append((topic, dict(payload))))
    _prime_pending_manage_flow(manage)

    result = manage.handle(_entry_like_fill_message())

    assert result is not None
    assert result.op == "ERR"
    assert result.verb == "TRADE_EXECUTED"
    assert result.pld["reason"] == "stale_local_lifecycle_conflict"
    assert manage.state == ManageState.BRACKETS_PENDING
    guard_event = next(payload for topic, payload in observed if topic == "EVT:EXECUTION_GUARD_BLOCKED")
    assert guard_event["block_reason"] == "stale_local_lifecycle_conflict"


def test_brackets_pending_trade_executed_tp_fill_reaches_shadow_observability(
    fsm_config,
    tmp_path: Path,
):
    shadow_path = tmp_path / "shadow.jsonl"
    fsm = FSMCore()
    journal = attach_shadow_journal(fsm, _shadow_cfg(shadow_path))
    assert journal is not None

    manage = ManageFlowFSM(config=fsm_config)
    manage.set_shadow_journal(journal)
    manage.set_observability_hook(
        lambda topic, payload: fsm.emit(
            topic,
            payload=payload,
            why=str(payload.get("why") or ""),
            rid=payload.get("rid"),
        )
    )
    _prime_pending_manage_flow(manage)

    result = manage.handle(_pending_tp_fill_message())

    assert result is not None
    records = _read_jsonl(shadow_path)
    event_names = {record["event_name"] for record in records}
    assert "EVT:EXIT_MATCH_ATTEMPTED" in event_names
    assert "DEC:CANCEL_ORDER" in event_names
    exit_match_record = next(
        record for record in records if record["event_name"] == "EVT:EXIT_MATCH_ATTEMPTED"
    )
    assert exit_match_record["payload_fragment"]["matched"] is True
    assert exit_match_record["payload_fragment"]["inferred_role"] == "TP"
    assert exit_match_record["payload_fragment"]["local_expected_ids_after"]["sl_order_id"] is None
    assert exit_match_record["payload_fragment"]["local_expected_ids_after"]["tp_order_id"] is None
