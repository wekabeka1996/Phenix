import json
from pathlib import Path
from types import SimpleNamespace


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
    import apps.reference.domains.execution_position.fsm as fsm_mod

    log_path = tmp_path / "trade_lifecycle.jsonl"
    fsm_mod._trade_lifecycle = TradeLifecycleLogger(log_file=str(log_path))

    class _EG:
        def __init__(self):
            self.state = SimpleNamespace(postfill_reservations={})

        def on_portfolio(self, _pld):
            return None

        def get_exposure_summary(self):
            return {}

        def expire_stale(self):
            return []

    fsm = fsm_mod.ExecPosFSM.__new__(fsm_mod.ExecPosFSM)
    fsm.exposure_guard = _EG()
    fsm._latest_portfolio_state = {}
    fsm._prev_position_amts = {"BTCUSDT": 1.0}
    fsm._last_position_closed_ts = {}
    fsm._last_any_position_closed_ts = 0.0
    fsm._open_regime_by_symbol = {"BTCUSDT": {"regime": "TEST"}}
    fsm._last_lifecycle_rid_by_symbol = {"BTCUSDT": "RID_CLOSE_1"}
    fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 123.45}
    fsm.order_guardian = None
    fsm.fsm = SimpleNamespace(order_index=None)
    fsm._get_async_loop = lambda: None

    # Trigger close: prev had position, current is 0
    event = SimpleNamespace(pld={"positions": [{"symbol": "BTCUSDT", "positionAmt": 0.0}]})
    fsm._on_portfolio_state_updated(event)

    assert log_path.exists()
    row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["rid"] == "RID_CLOSE_1"
    assert row["status"] == "CLOSED"
    assert row["close_reason"] == "POSITION_CLOSED_DETECTED"
    assert float(row["close_price"]) == 123.45
