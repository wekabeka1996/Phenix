from __future__ import annotations

import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.reference.config_models import (
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionStartupTruthArtifactConfig,
)
from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
from apps.reference.domains.execution_position.fsm_manage import ManageState
from apps.reference.domains.execution_position.order_index import OrderIndex
from apps.reference.domains.execution_position.restore_artifact import (
    TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN,
)
from vfoundation.dr import wal as vwal


class _DummyFSMCore:
    def __init__(self, order_index=None):
        self.order_index = order_index
        self.emitted: list[tuple[str, dict, str]] = []

    def emit(self, event_name: str, payload: dict, rid: str) -> None:
        self.emitted.append((event_name, payload, rid))


@pytest.mark.asyncio
async def test_startup_reconcile_reconstructs_runtime_brackets_without_flat_contamination(
    fsm_harness,
    tmp_path,
) -> None:
    fsm, _, _ = fsm_harness
    symbol = "ETHUSDT"
    fsm._trade_lifecycle_log_path = lambda: str(
        tmp_path / "trade_lifecycle.jsonl")
    restore_path = tmp_path / "execution_restore.json"
    startup_truth_path = tmp_path / "execution_startup_truth.jsonl"
    fsm.config.domains.execution_position.restore_artifact = ExecutionPositionRestoreArtifactConfig(
        mode="writer_only",
        storage_path=str(restore_path),
        flush_interval_ms=250,
        dark_read_max_artifact_age_ms=300000,
    )
    fsm._startup_truth_orchestrator._restore_artifact_writer = fsm._startup_truth_orchestrator._create_restore_artifact_writer()
    fsm.config.domains.execution_position.startup_truth_artifact = (
        ExecutionPositionStartupTruthArtifactConfig(
            mode="writer_only",
            storage_path=str(startup_truth_path),
        )
    )
    fsm._startup_truth_orchestrator._startup_truth_artifact_writer = fsm._startup_truth_orchestrator._create_startup_truth_artifact_writer()

    wal_dir = tmp_path / "wal"
    vwal.set_wal_dir(wal_dir)
    wal_dir.mkdir(parents=True, exist_ok=True)
    wal_path = wal_dir / f"{date.today().isoformat()}.jsonl"
    wal_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "rid": "r1",
                        "op": "EVT",
                        "verb": "ORDER_PLACED",
                        "ts": 1,
                        "symbol": symbol,
                        "order_id": "oid-1",
                        "client_order_id": "cid-1",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "rid": "r2",
                        "op": "EVT",
                        "verb": "ORDER_STATE_CHANGED",
                        "ts": 2,
                        "symbol": symbol,
                        "order_id": "oid-2",
                        "status": "FILLED",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manage_flow = MagicMock()
    manage_flow.state = ManageState.FLAT
    manage_flow.set_bracket_ids = MagicMock()
    manage_flow.has_active_lifecycle.return_value = False
    fsm.manage_flows[symbol] = manage_flow
    fsm.fsm.order_index = OrderIndex(ttl_sec=600)

    fsm.adapter = MagicMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": symbol, "positionAmt": "0.10"}]
    )
    open_orders = [
        {
            "symbol": symbol,
            "orderId": "8631145709",
            "clientOrderId": "exchange-algo-sl",
            "side": "SELL",
            "type": "STOP_MARKET",
        },
        {
            "symbol": symbol,
            "orderId": "8631145710",
            "clientOrderId": "exchange-algo-tp",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
        },
    ]
    fsm.adapter.get_open_orders = AsyncMock(
        side_effect=[open_orders, open_orders])

    fsm.order_guardian.link_existing_from_rest = AsyncMock()
    fsm.order_guardian.cleanup_orphans = AsyncMock()

    def _resolve_context(*, client_order_id, exchange_order_id, symbol=None):
        if exchange_order_id == "8631145709":
            return {
                "symbol": symbol,
                "rid": "aurora_ETHUSDT_1775247901546",
                "parent_entry_order_id": "entry-eth-1",
                "tracked_bracket_order_id": "8631145709",
                "tracked_client_order_id": "SL-ETHUSDT-1",
                "bracket_role": "SL",
                "order_type": "STOP_MARKET",
                "reduce_only": True,
                "close_position": True,
            }
        if exchange_order_id == "8631145710":
            return {
                "symbol": symbol,
                "rid": "aurora_ETHUSDT_1775247901546",
                "parent_entry_order_id": "entry-eth-1",
                "tracked_bracket_order_id": "8631145710",
                "tracked_client_order_id": "TP-ETHUSDT-1",
                "bracket_role": "TP",
                "order_type": "TAKE_PROFIT_MARKET",
                "reduce_only": True,
                "close_position": True,
            }
        return None

    fsm.order_guardian.resolve_terminal_bracket_context = MagicMock(
        side_effect=_resolve_context
    )

    await fsm._startup_order_guardian_reconcile()

    assert fsm._symbol_brackets[symbol] == {
        "sl_order_id": "8631145709",
        "tp_order_id": "8631145710",
    }
    assert fsm._symbol_bracket_truth_source[symbol] == TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN
    assert fsm.fsm.order_index.get(exchangeOrderId="8631145709") is not None
    assert fsm.fsm.order_index.get(exchangeOrderId="8631145710") is not None
    manage_flow.set_bracket_ids.assert_not_called()

    rows = [
        json.loads(line)
        for line in (tmp_path / "trade_lifecycle.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        row.get("event_type") == "EXECUTION_RESTART_RUNTIME_TRUTH_RECONSTRUCTED"
        and row.get("symbol") == symbol
        for row in rows
    )

    startup_rows = [
        json.loads(line)
        for line in startup_truth_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(startup_rows) == 1
    startup_row = startup_rows[0]
    assert startup_row["artifact_type"] == "execution_position_startup_truth_v1"
    assert startup_row["startup_trigger"] == "startup_order_guardian_reconcile"
    assert startup_row["symbols_considered"] == [symbol]
    assert startup_row["fresh_open_order_count"] == 2
    assert startup_row["reconcile_sequence"] == [
        "authoritative_restore_read",
        "collect_startup_symbols",
        "guardian_link_existing_from_rest",
        "guardian_cleanup_orphans",
        "fetch_post_cleanup_open_orders",
        "reconstruct_runtime_bracket_truth",
        "dark_read_compare",
        "persist_restore_artifact_snapshot",
    ]
    assert startup_row["input_snapshot"]["positions_fetch_succeeded"] is True
    assert startup_row["input_snapshot"]["pre_cleanup_open_orders_fetch_succeeded"] is True
    assert startup_row["input_snapshot"]["post_cleanup_open_orders_fetch_succeeded"] is True
    assert startup_row["input_snapshot"]["guardian_link_existing_invoked"] is True
    assert startup_row["input_snapshot"]["guardian_cleanup_invoked"] is True
    assert startup_row["runtime_truth_summary"] == {
        "symbols_reconstructed": 1,
        "order_index_registrations": 2,
        "unresolved_symbols": 0,
    }
    assert startup_row["runtime_truth_records"] == [
        {
            "symbol": symbol,
            "status": "reconstructed",
            "sl_order_id": "8631145709",
            "tp_order_id": "8631145710",
            "bracket_truth_source": "RECONSTRUCTED_GUARDIAN",
            "manage_truth_source": "RUNTIME_LOCAL",
            "order_index_registrations": 2,
            "unresolved_reasons": [],
        }
    ]
    assert startup_row["unknown_truth_records"] == []
    assert startup_row["restore_artifact"] == {
        "path": str(restore_path),
        "write_attempted": True,
        "write_succeeded": True,
    }
    assert startup_row["bounded_replay_summary"]["boundary_name"] == "W5"
    assert startup_row["bounded_replay_summary"]["source_kind"] == "canonical_wal"
    assert startup_row["bounded_replay_summary"]["scan_state"] == "completed"
    assert startup_row["bounded_replay_summary"]["symbols_considered"] == [
        symbol]
    assert startup_row["bounded_replay_summary"]["records_seen"] == 1
    assert startup_row["bounded_replay_summary"]["records_accepted"] == 1
    assert startup_row["bounded_replay_summary"]["records_ignored_by_boundary"] == 1
    assert startup_row["bounded_replay_summary"]["restore_boundary_separation"] == "report_only"
    assert startup_row["bounded_replay_summary"]["authoritative_mutation_attempted"] is False
    assert startup_row["execution_truth_cache"]["truth_class"] == "cache_only"
    assert startup_row["execution_truth_cache"]["authoritative"] is False


@pytest.mark.asyncio
async def test_startup_reconcile_leaves_unresolved_truth_fail_closed_when_guardian_proof_missing(
    fsm_harness,
    tmp_path,
) -> None:
    fsm, _, _ = fsm_harness
    symbol = "ETHUSDT"
    fsm._trade_lifecycle_log_path = lambda: str(
        tmp_path / "trade_lifecycle.jsonl")
    fsm.fsm.order_index = OrderIndex(ttl_sec=600)

    fsm.adapter = MagicMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": symbol, "positionAmt": "0.10"}]
    )
    open_orders = [
        {
            "symbol": symbol,
            "orderId": "8631145799",
            "clientOrderId": "mystery-client-id",
            "side": "SELL",
            "type": "STOP_MARKET",
        }
    ]
    fsm.adapter.get_open_orders = AsyncMock(
        side_effect=[open_orders, open_orders])

    fsm.order_guardian.link_existing_from_rest = AsyncMock()
    fsm.order_guardian.cleanup_orphans = AsyncMock()
    fsm.order_guardian.resolve_terminal_bracket_context = MagicMock(
        return_value=None)

    await fsm._startup_order_guardian_reconcile()

    assert symbol not in fsm._symbol_brackets
    assert fsm.fsm.order_index.get(exchangeOrderId="8631145799") is None


@pytest.mark.asyncio
async def test_ws_terminal_hit_after_startup_reconstruction_uses_rebuilt_order_index(
    fsm_harness,
    tmp_path,
) -> None:
    fsm, _, _ = fsm_harness
    symbol = "ETHUSDT"
    fsm._trade_lifecycle_log_path = lambda: str(
        tmp_path / "trade_lifecycle.jsonl")
    fsm.fsm.order_index = OrderIndex(ttl_sec=600)

    fsm.adapter = MagicMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": symbol, "positionAmt": "0.10"}]
    )
    open_orders = [
        {
            "symbol": symbol,
            "orderId": "8631145709",
            "clientOrderId": "exchange-algo-sl",
            "side": "SELL",
            "type": "STOP_MARKET",
        }
    ]
    fsm.adapter.get_open_orders = AsyncMock(
        side_effect=[open_orders, open_orders])

    fsm.order_guardian.link_existing_from_rest = AsyncMock()
    fsm.order_guardian.cleanup_orphans = AsyncMock()
    fsm.order_guardian.resolve_terminal_bracket_context = MagicMock(
        return_value={
            "symbol": symbol,
            "rid": "aurora_ETHUSDT_1775247901546",
            "parent_entry_order_id": "entry-eth-1",
            "tracked_bracket_order_id": "8631145709",
            "tracked_client_order_id": "SL-ETHUSDT-1",
            "bracket_role": "SL",
            "order_type": "STOP_MARKET",
            "reduce_only": True,
            "close_position": True,
        }
    )

    await fsm._startup_order_guardian_reconcile()

    fsm_core = _DummyFSMCore(order_index=fsm.fsm.order_index)
    client = BinanceWebSocketClient(
        api_key="k",
        base_url="http://example.invalid",
        use_testnet=True,
        fsm_core=fsm_core,
    )

    msg = {
        "e": "ORDER_TRADE_UPDATE",
        "T": 1710000123456,
        "o": {
            "c": "runtime-client-algo-id",
            "i": "8631145709",
            "X": "FILLED",
            "s": symbol,
            "z": "0.10",
            "l": "0.10",
            "S": "SELL",
            "o": "STOP_MARKET",
            "q": "0.10",
            "ap": "1990.0",
            "p": "1990.0",
        },
    }

    client._handle_ws_message(msg)
    await asyncio.sleep(0)

    assert len(fsm_core.emitted) == 1
    event_name, payload, rid = fsm_core.emitted[0]
    assert event_name == "EVT:TRADE_EXECUTED"
    assert rid == "WS_ORDER_UPDATE_FILLED"
    assert payload["rid"] == "aurora_ETHUSDT_1775247901546:SL"
    assert payload["bracket_role"] == "SL"
    assert payload["terminal_correlation_source"] == "order_index_canonical"
