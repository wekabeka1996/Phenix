import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_trade_lifecycle_logger_persists_live_snapshots_and_terminal_row(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from apps.reference.telemetry.trade_lifecycle_logger import (
        TRADE_LIFECYCLE_SNAPSHOT_RECORD_KIND,
        TradeLifecycleLogger,
    )

    log_path = tmp_path / "logs" / "trade_lifecycle.jsonl"
    logger = TradeLifecycleLogger(log_file=str(log_path))

    assert not log_path.exists()

    logger.on_intent(
        rid="RID1",
        symbol="BTCUSDT",
        side="LONG",
        regime="TEST",
        confidence=0.5,
        strategy_id="s",
        entry_type="LIMIT",
    )
    assert not log_path.exists()

    logger.on_order_placed(rid="RID1", order_id="OID1", price=99.5)
    logger.on_fill(rid="RID1", fill_price=100.0, fill_qty=0.01, fees=0.0)
    logger.on_fill(rid="RID1", fill_price=100.0, fill_qty=0.01, fees=0.0)
    logger.on_close(rid="RID1", close_price=101.0, close_reason="TEST_CLOSE", pnl_pct=0.01, pnl_usdt=1.0)

    assert log_path.exists()
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3

    ordered = rows[0]
    assert ordered["record_kind"] == TRADE_LIFECYCLE_SNAPSHOT_RECORD_KIND
    assert ordered["event_type"] == "TRADE_LIFECYCLE_ORDERED"
    assert ordered["status"] == "ORDERED"
    assert ordered["order_id"] == "OID1"

    filled = rows[1]
    assert filled["record_kind"] == TRADE_LIFECYCLE_SNAPSHOT_RECORD_KIND
    assert filled["event_type"] == "TRADE_LIFECYCLE_FILLED"
    assert filled["status"] == "FILLED"
    assert float(filled["fill_price"]) == 100.0
    assert float(filled["fill_qty"]) == 0.01

    row = rows[2]
    assert row["rid"] == "RID1"
    assert row["status"] == "CLOSED"
    assert row["close_reason"] == "TEST_CLOSE"


def test_trade_lifecycle_snapshots_remain_searchable_after_restart(tmp_path):
    from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger

    log_path = tmp_path / "trade_lifecycle.jsonl"
    first_logger = TradeLifecycleLogger(log_file=str(log_path), orphan_ttl_sec=3600)

    first_logger.on_intent(
        rid="RID-RESTART-1",
        symbol="ETHUSDT",
        side="SELL",
        strategy_id="aurora",
        entry_type="LIMIT",
    )
    first_logger.on_order_placed(rid="RID-RESTART-1", order_id="OID-RESTART-1", price=2178.4)
    first_logger.on_fill(rid="RID-RESTART-1", fill_price=2178.4, fill_qty=0.02, fees=0.03)

    pre_restart_rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(pre_restart_rows) == 2
    assert pre_restart_rows[0]["event_type"] == "TRADE_LIFECYCLE_ORDERED"
    assert pre_restart_rows[0]["order_id"] == "OID-RESTART-1"
    assert pre_restart_rows[1]["event_type"] == "TRADE_LIFECYCLE_FILLED"
    assert float(pre_restart_rows[1]["fill_qty"]) == 0.02

    restarted_logger = TradeLifecycleLogger(log_file=str(log_path), orphan_ttl_sec=3600)
    restarted_logger.on_close(
        rid="RID-RESTART-1",
        close_price=2177.9,
        close_reason="POSITION_CLOSED_DETECTED",
    )

    post_restart_rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(post_restart_rows) == 3
    assert post_restart_rows[0]["event_type"] == "TRADE_LIFECYCLE_ORDERED"
    assert post_restart_rows[1]["event_type"] == "TRADE_LIFECYCLE_FILLED"
    assert post_restart_rows[2]["rid"] == "RID-RESTART-1"
    assert post_restart_rows[2]["status"] == "CLOSED"
    assert post_restart_rows[2]["close_reason"] == "POSITION_CLOSED_DETECTED"


def test_execpos_portfolio_close_triggers_trade_lifecycle_close(tmp_path, monkeypatch):
    from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    log_path = tmp_path / "trade_lifecycle.jsonl"
    tl_logger = TradeLifecycleLogger(log_file=str(log_path))

    # Mock ExecPosFSM
    mock_fsm = MagicMock()
    mock_fsm._latest_portfolio_state = {}
    mock_fsm._prev_position_amts = {"BTCUSDT": 1.0}
    mock_fsm._last_lifecycle_rid_by_symbol = {"BTCUSDT": "RID_CLOSE_1"}
    mock_fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 123.45}
    mock_fsm._open_regime_by_symbol = {"BTCUSDT": {"regime": "TEST"}}
    mock_fsm._last_position_closed_ts = {}
    mock_fsm.exposure_guard = MagicMock()
    mock_fsm.exposure_guard.get_exposure_summary.return_value = {}
    mock_fsm.exposure_guard.expire_stale.return_value = []
    mock_fsm.exposure_guard.state.postfill_reservations = {}
    mock_fsm.log_adapter = MagicMock()
    mock_fsm._get_async_loop.return_value = None
    
    event = SimpleNamespace(pld={"positions": [{"symbol": "BTCUSDT", "positionAmt": 0.0}]})
    
    # We need to patch BOTH the global logger in handlers_mod AND get_clock
    with patch("apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle", tl_logger), \
         patch("apps.reference.domains.execution_position.orchestration.event_handlers.get_clock") as mock_clock:
        
        mock_clock.return_value.now_sec.return_value = 1000.0
        mock_clock.return_value.now_ms.return_value = 1000000
        
        handler = handlers_mod.EPEventHandlers(mock_fsm)
        handler.on_portfolio_state_updated(event)

    assert log_path.exists()
    row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["rid"] == "RID_CLOSE_1"
    assert row["status"] == "CLOSED"
    assert row["close_reason"] == "POSITION_CLOSED_DETECTED"
    assert float(row["close_price"]) == 123.45


def test_trade_lifecycle_reconciles_boundary_reject_after_late_order_and_fill(tmp_path):
    from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger

    log_path = tmp_path / "trade_lifecycle.jsonl"
    logger = TradeLifecycleLogger(log_file=str(log_path), orphan_ttl_sec=3600)

    rid = "RID-RACE-1"
    logger.on_intent(rid=rid, symbol="ETHUSDT", side="SELL", strategy_id="aurora")
    logger.on_reject(
        rid=rid,
        reject_reason="trade_intent_boundary_audit:no_downstream_event",
        reject_reason_code="NRR-EXECUTION-NO-DOWNSTREAM-EVENT",
        reject_stage="EXECUTION",
    )
    logger.on_order_placed(rid=rid, order_id="8617505424", price=2176.61)
    logger.on_fill(rid=rid, fill_price=2176.61, fill_qty=0.01, fees=0.02)
    logger.on_close(rid=rid, close_price=2175.10, close_reason="POSITION_CLOSED_DETECTED")

    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4

    assert rows[0]["rid"] == rid
    assert rows[0]["status"] == "REJECTED"
    assert rows[0]["reject_reason_code"] == "NRR-EXECUTION-NO-DOWNSTREAM-EVENT"
    assert rows[0]["reject_stage"] == "EXECUTION"

    assert rows[1]["record_kind"] == "trade_lifecycle_snapshot"
    assert rows[1]["event_type"] == "TRADE_LIFECYCLE_ORDERED"
    assert rows[1]["status"] == "ORDERED"
    assert rows[1]["order_id"] == "8617505424"

    assert rows[2]["record_kind"] == "trade_lifecycle_snapshot"
    assert rows[2]["event_type"] == "TRADE_LIFECYCLE_FILLED"
    assert rows[2]["status"] == "FILLED"

    assert rows[3]["rid"] == rid
    assert rows[3]["status"] == "CLOSED"
    assert rows[3]["order_id"] == "8617505424"
    assert rows[3]["prior_terminal_status"] == "REJECTED"
    assert rows[3]["prior_terminal_reason"] == "trade_intent_boundary_audit:no_downstream_event"
    assert rows[3]["reconciliation_source"] == "order_placed"
    assert rows[3]["close_reason"] == "POSITION_CLOSED_DETECTED"
    assert not any(row["status"] == "ORPHANED_TTL" for row in rows)


def test_trade_lifecycle_terminal_deduplicates_repeated_cancel(tmp_path):
    from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger

    log_path = tmp_path / "trade_lifecycle.jsonl"
    logger = TradeLifecycleLogger(log_file=str(log_path), orphan_ttl_sec=3600)

    logger.on_intent(rid="RID-CANCEL-1", symbol="SOLUSDT", side="BUY", strategy_id="aurora")
    logger.on_order_placed(rid="RID-CANCEL-1", order_id="OID-CANCEL-1", price=123.4)
    logger.on_cancel(rid="RID-CANCEL-1", cancel_reason="timeout_cancellation")
    logger.on_cancel(rid="RID-CANCEL-1", cancel_reason="timeout_cancellation")

    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["event_type"] == "TRADE_LIFECYCLE_ORDERED"
    assert rows[1]["status"] == "CANCELLED"
    assert rows[1]["close_reason"] == "timeout_cancellation"


def test_trade_lifecycle_preserves_explicit_null_regime_contract(tmp_path):
    from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger

    log_path = tmp_path / "trade_lifecycle.jsonl"
    logger = TradeLifecycleLogger(log_file=str(log_path), orphan_ttl_sec=3600)

    logger.on_intent(
        rid="RID-NULL-REGIME-1",
        symbol="BTCUSDT",
        side="BUY",
        regime="",
        confidence=None,
        regime_provenance=None,
        strategy_id="llm_microstructure",
        entry_type="LIMIT",
    )
    logger.on_order_placed(
        rid="RID-NULL-REGIME-1",
        order_id="OID-NULL-REGIME-1",
        price=101.5,
        regime="",
        confidence=None,
        regime_provenance=None,
    )
    logger.on_cancel(rid="RID-NULL-REGIME-1", cancel_reason="external_path_cancelled")

    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2

    ordered = rows[0]
    terminal = rows[1]

    for row in (ordered, terminal):
        assert "regime" in row and row["regime"] is None
        assert "regime_confidence" in row and row["regime_confidence"] is None
        assert "regime_provenance" in row and row["regime_provenance"] is None
        assert "execution_regime" in row and row["execution_regime"] is None
        assert "execution_regime_confidence" in row and row["execution_regime_confidence"] is None
        assert "execution_regime_provenance" in row and row["execution_regime_provenance"] is None
