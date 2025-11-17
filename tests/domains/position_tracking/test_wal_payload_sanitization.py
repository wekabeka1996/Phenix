"""PositionTracking WAL payload sanitization tests."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest

from vfoundation.core.protocol import Message
from vfoundation.dr import wal
from apps.reference.domains.position_tracking.position_tracking import PositionTracking


@pytest.fixture
def temp_wal_dir(tmp_path):
    """Create an isolated WAL directory for sanitization tests."""
    wal_dir = tmp_path / "wal_sanitize"
    wal_dir.mkdir()
    wal.set_wal_dir(wal_dir)
    yield wal_dir
    from vfoundation.config import config

    wal.set_wal_dir(config.wal_dir)


@pytest.fixture
def position_tracking_domain(temp_wal_dir):
    """PositionTracking domain wired with a mock FSM for WAL tests."""
    fsm = MagicMock()
    fsm.emit = MagicMock()
    fsm.listen = MagicMock()

    config = {
        "risk_budgets": {"ETHUSDT": {"max_position_size_usd": 10000}},
        "instruments": {"ETHUSDT": {"min_qty": 0.001}},
    }
    return PositionTracking(fsm=fsm, config=config)


def test_magicmock_payload_is_sanitized(position_tracking_domain, temp_wal_dir, caplog):
    """MagicMock objects must be coerced to JSON-safe strings before WAL serialization."""
    rid_object = MagicMock(name="RID-mock")
    payload = {
        "symbol": "ETHUSDT",
        "side": "buy",
        "quantity": 0.25,
        "price": 2100.0,
        "commission": 0.21,
        "ts": 1731542400000,
        "venue": "binance",
        "debug": {"problem_value": MagicMock(name="payload-mock")},
    }

    event = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld=payload,
        src="test",
        dst="position_tracking",
        rid="RID-placeholder",
    )

    # Simulate downstream mutation that injects a MagicMock rid
    event.rid = rid_object  # type: ignore[attr-defined]

    caplog.set_level(logging.WARNING, logger="vfoundation.dr.wal")

    position_tracking_domain.on_trade_executed(event)

    wal_file_path = wal._get_wal_file_path()
    assert wal_file_path.exists(), "WAL file missing after append"

    with wal_file_path.open("r", encoding="utf-8") as handle:
        last_entry = json.loads(handle.readlines()[-1])

    sanitized_rid = last_entry["rid"]
    assert isinstance(sanitized_rid, str)
    assert "MagicMock" in sanitized_rid

    debug_value = last_entry["pld"]["debug"]["problem_value"]
    assert isinstance(debug_value, str)
    assert "MagicMock" in debug_value

    assert any(
        "WAL sanitize" in message for message in caplog.messages
    ), "Sanitization warning was not emitted"
