import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_trade_lifecycle_logger_creates_file_only_on_flush(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger

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

    logger.on_fill(rid="RID1", fill_price=100.0, fill_qty=0.01, fees=0.0)
    assert not log_path.exists()

    logger.on_close(rid="RID1", close_price=101.0, close_reason="TEST_CLOSE", pnl_pct=0.01, pnl_usdt=1.0)

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["rid"] == "RID1"
    assert row["status"] == "CLOSED"
    assert row["close_reason"] == "TEST_CLOSE"


def test_execpos_portfolio_close_triggers_trade_lifecycle_close(tmp_path, monkeypatch):
    from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger
    import apps.reference.domains.execution_position.event_handlers as handlers_mod
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
    with patch("apps.reference.domains.execution_position.event_handlers._trade_lifecycle", tl_logger), \
         patch("apps.reference.domains.execution_position.event_handlers.get_clock") as mock_clock:
        
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
