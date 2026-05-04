import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message

from apps.reference.domains.position_tracking.position_tracking import PositionTracking


class _FakeFSM:
    def __init__(self, exec_pos=None):
        self.domains = {}
        if exec_pos is not None:
            self.domains["execution_position"] = exec_pos
        self.listen = MagicMock()
        self.emit = MagicMock()


def _build_config():
    config = MagicMock()

    pt_config = MagicMock()
    pt_config.enable_market_tick_subscription = False
    precision = MagicMock()
    precision.quantity_min_threshold = 0.0001
    precision.flat_position_threshold = 0.0001
    precision.decimal_places = 4
    pt_config.precision = precision

    domains = MagicMock()
    domains.position_tracking = pt_config
    config.domains = domains

    exposure = MagicMock()
    exposure.leverage_defaults = {"__default__": "10.0"}
    execution = MagicMock()
    execution.exposure = exposure
    trading = MagicMock()
    trading.execution = execution
    config.trading = trading

    eth_spec = MagicMock()
    eth_spec.execution.target_leverage = 20
    config.instruments = {"ETHUSDT": eth_spec}
    return config


def _account_update_event() -> Message:
    return Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="binance_ws_client",
        dst="position_tracking",
        rid="acct-update-1",
        pld={
            "totalWalletBalance": "10000",
            "totalUnrealizedProfit": "0",
            "positions": [],
        },
    )


def _read_records(log_path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_proven_terminal_close_prevents_false_manual_disappearance_attribution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    exec_pos = MagicMock()
    exec_pos.get_recent_terminal_close_proof.return_value = {
        "symbol": "ETHUSDT",
        "rid": "aurora_ETHUSDT_1775247901546",
        "close_reason": "SL",
        "tracked_bracket_order_id": "1000000041481020",
        "parent_entry_order_id": "entry-eth-1",
        "terminal_correlation_source": "order_guardian_client_order_id",
        "source": "exchange_bracket_websocket",
        "ts_ms": 1710000123456,
    }

    tracker = PositionTracking(_FakeFSM(exec_pos), _build_config())
    tracker.alert_manager = MagicMock()
    tracker._positions["ETHUSDT"] = {
        "quantity": Decimal("0.10"),
        "avg_price": Decimal("2000"),
        "venues": ["binance"],
    }

    tracker.on_account_update(_account_update_event())

    assert "ETHUSDT" not in tracker._positions
    assert tracker.manual_intervention_detected_total == 0
    tracker.alert_manager.check_position_disappearance.assert_not_called()
    tracker.alert_manager.check_manual_intervention.assert_not_called()

    rows = _read_records(tmp_path / "logs" / "trade_lifecycle.jsonl")
    assert rows[0]["record_kind"] == "position_disappearance"
    assert rows[0]["attribution"] == "proven_exchange_bracket_close"
    assert rows[0]["close_reason"] == "SL"
    assert rows[0]["tracked_bracket_order_id"] == "1000000041481020"
    assert rows[0]["proof_source"] == "exchange_bracket_websocket"


def test_unproven_disappearance_stays_fail_closed_and_non_manual(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    tracker = PositionTracking(_FakeFSM(), _build_config())
    tracker.alert_manager = MagicMock()
    tracker._positions["ETHUSDT"] = {
        "quantity": Decimal("0.10"),
        "avg_price": Decimal("2000"),
        "venues": ["binance"],
    }

    tracker.on_account_update(_account_update_event())

    assert "ETHUSDT" not in tracker._positions
    assert tracker.manual_intervention_detected_total == 1
    tracker.alert_manager.check_position_disappearance.assert_called_once()
    tracker.alert_manager.check_manual_intervention.assert_not_called()

    rows = _read_records(tmp_path / "logs" / "trade_lifecycle.jsonl")
    assert rows[0]["record_kind"] == "position_disappearance"
    assert rows[0]["attribution"] == "unknown_disappearance"
    assert "close_reason" not in rows[0]
