import json
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from vfoundation.core.protocol import Message
from vfoundation.dr import wal

from apps.reference.domains.position_tracking.position_tracking import PositionTracking


@pytest.fixture
def mock_fsm():
    fsm = Mock()
    fsm.listen = Mock()
    fsm.emit = Mock()
    return fsm


@pytest.fixture
def mock_config():
    config = MagicMock()

    pt_config = MagicMock()
    pt_config.enable_market_tick_subscription = False
    pt_config.positions_stale_ttl_sec = 60.0

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

    # SSOT: instruments.yaml leverage
    btcusdt_spec = MagicMock()
    btcusdt_spec.execution.target_leverage = 50
    btcusdt_spec.execution.margin_mode = "cross"
    config.instruments = {"BTCUSDT": btcusdt_spec}

    return config


def test_position_tracking_wal_timestamp_is_epoch_ms(tmp_path, mock_fsm, mock_config):
    original_wal_dir = wal.WAL_DIR
    wal.set_wal_dir(tmp_path)
    try:
        tracker = PositionTracking(mock_fsm, mock_config)

        trade_event = Message(
            op="EVT",
            verb="EVT:TRADE_EXECUTED",
            pld={
                "symbol": "BTCUSDT",
                "side": "buy",
                "price": "50000",
                "quantity": "0.01",
                "fees": "0",
                "venue": "binance",
                "ts": 1700000000000,
            },
            src="execution",
            dst="position_tracking",
            rid="RID-wal-ms",
        )

        tracker.on_trade_executed(trade_event)

        wal_file = wal._get_wal_file_path()
        last_line = wal_file.read_text(encoding="utf-8").strip().splitlines()[-1]
        record = json.loads(last_line)

        assert isinstance(record.get("timestamp"), int)
        assert record["timestamp"] > 1_700_000_000_000
        assert record["timestamp"] < 10_000_000_000_000  # sanity: ms, not us/ns
    finally:
        wal.set_wal_dir(original_wal_dir)


def test_main_wires_inflight_reconciler():
    main_src = Path("apps/reference/main.py").read_text(encoding="utf-8")
    assert "InFlightReconciler" in main_src
    assert "EVT:ORDER_ACK" in main_src
    assert "run_forever" in main_src

