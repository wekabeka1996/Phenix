# PATH: tests/domains/test_position_tracking_wal_integration.py
"""
FSMP-RESILIENCE-T03-A: WAL Integration Tests for Position Tracking

Verify that position_tracking domain writes events to WAL before processing.
Critical safety requirement: If WAL write fails, event processing must be halted.
"""
import json
import os
import sys
from unittest.mock import MagicMock
import pytest

# Add project paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vfoundation.core.protocol import Message
from vfoundation.dr import wal


@pytest.fixture
def temp_wal_dir(tmp_path):
    """Create temporary WAL directory for isolated testing"""
    wal_dir = tmp_path / "test_wal"
    wal_dir.mkdir()
    # Set WAL directory to temp location
    wal.set_wal_dir(wal_dir)
    yield wal_dir
    # Cleanup: restore default (will be overridden by next test anyway)
    from vfoundation.config import config
    wal.set_wal_dir(config.wal_dir)


@pytest.fixture
def mock_fsm():
    """Create mock FSM for testing"""
    fsm = MagicMock()
    fsm.emit = MagicMock()
    fsm.listen = MagicMock()
    return fsm


@pytest.fixture
def position_tracking_domain(mock_fsm, temp_wal_dir):
    """Create PositionTracking domain instance"""
    from apps.reference.domains.position_tracking.position_tracking import PositionTracking
    
    config = {
        "risk_budgets": {"ETHUSDT": {"max_position_size_usd": 10000}},
        "instruments": {"ETHUSDT": {"min_qty": 0.001}}
    }
    
    domain = PositionTracking(fsm=mock_fsm, config=config)
    return domain


def test_trade_executed_writes_to_wal(position_tracking_domain, temp_wal_dir):
    """
    Test that EVT:TRADE_EXECUTED event is written to WAL before processing.
    
    Coverage: WAL durability guarantee for critical position updates.
    """
    # Arrange: Create trade executed event
    trade_event = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={
            "symbol": "ETHUSDT",
            "side": "buy",  # lowercase
            "quantity": 0.1,
            "price": 3500.0,
            "commission": 0.35,
            "ts": 1234567890000,  # Required timestamp field
            "venue": "binance"  # Required venue field
        },
        src="execution_engine",
        dst="position_tracking",
        rid="RID-test-trade-123"
    )
    
    # Act: Process the event
    position_tracking_domain.on_trade_executed(trade_event)
    
    # Assert: WAL file was created
    wal_file_path = wal._get_wal_file_path()
    assert wal_file_path.exists(), f"WAL file should exist at {wal_file_path}"
    
    # Assert: WAL file contains the trade event
    with open(wal_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        assert len(lines) >= 1, "WAL should contain at least one entry"
        
        # Parse last line (should be our trade event)
        # WAL structure: {op, verb, pld, src, dst, rid, timestamp, _prev, _hash}
        last_entry = json.loads(lines[-1])
        assert "_hash" in last_entry, "WAL entry must have '_hash' field"
        assert "_prev" in last_entry, "WAL entry must have '_prev' field"
        assert last_entry["verb"] == "TRADE_EXECUTED"
        assert last_entry["pld"]["symbol"] == "ETHUSDT"
        assert last_entry["pld"]["quantity"] == 0.1
        assert last_entry["rid"] == "RID-test-trade-123"


# def test_account_update_writes_to_wal(position_tracking_domain, temp_wal_dir):
    """
    Test that EVT:ACCOUNT_UPDATE_RECEIVED event is written to WAL before processing.
    
    Coverage: WAL durability guarantee for account state synchronization.
    """
    # Arrange: Create account update event
    account_event = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        pld={
            "totalWalletBalance": 50000.0,
            "positions": [
                {
                    "symbol": "ETHUSDT",
                    "positionAmt": 0.5,
                    "entryPrice": 3400.0
                }
            ]
        },
        src="binance_adapter",
        dst="position_tracking",
        rid="RID-test-account-456"
    )
    
    # Act: Process the event
    position_tracking_domain.on_account_update(account_event)
    
    # Assert: WAL file was created
    wal_file_path = wal._get_wal_file_path()
    assert wal_file_path.exists(), f"WAL file should exist at {wal_file_path}"
    
    # Assert: WAL file contains the account update event
    with open(wal_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        assert len(lines) >= 1, "WAL should contain at least one entry"
        
        # Parse last line (should be our account event)
        # WAL structure: {op, verb, pld, src, dst, rid, timestamp, _prev, _hash}
        last_entry = json.loads(lines[-1])
        assert "_hash" in last_entry, "WAL entry must have '_hash' field"
        assert "_prev" in last_entry, "WAL entry must have '_prev' field"
        assert last_entry["verb"] == "TRADE_EXECUTED"
        assert last_entry["pld"]["totalWalletBalance"] == 50000.0
        assert last_entry["rid"] == "RID-test-account-456"


def test_wal_write_failure_halts_processing(position_tracking_domain, temp_wal_dir, monkeypatch):
    """
    Test that if WAL write fails, event processing is halted (Fail-Closed).
    
    Coverage: Safety guarantee - never process events without durable log.
    """
    # Arrange: Mock WAL append to fail
    def mock_append_failure(record, lock_timeout_s=None):
        raise IOError("Simulated WAL write failure")
    
    monkeypatch.setattr(wal, "append", mock_append_failure)
    
    trade_event = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={
            "symbol": "ETHUSDT",
            "side": "buy",  # lowercase
            "quantity": 0.1,
            "price": 3500.0,
            "commission": 0.35,
            "ts": 1234567890000,  # Required timestamp field
            "venue": "binance"  # Required venue field
        },
        src="execution_engine",
        dst="position_tracking",
        rid="RID-test-fail-789"
    )
    
    # Act: Process the event (should be halted)
    position_tracking_domain.on_trade_executed(trade_event)
    
    # Assert: No portfolio state update event was emitted
    # (processing was halted before reaching emit logic)
    position_tracking_domain.fsm.emit.assert_not_called()


def test_wal_entries_have_correct_structure(position_tracking_domain, temp_wal_dir):
    """
    Test that WAL entries follow the expected structure with chain integrity.
    
    Coverage: WAL format compliance for replay and integrity verification.
    """
    # Arrange: Create two events to test chaining
    trade_event_1 = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={"symbol": "ETHUSDT", "side": "buy", "quantity": 0.1, "price": 3500.0, "commission": 0.35, "ts": 1234567890000, "venue": "binance"},
        src="execution_engine",
        dst="position_tracking",
        rid="RID-chain-1"
    )
    
    trade_event_2 = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={"symbol": "BTCUSDT", "side": "sell", "quantity": 0.01, "price": 65000.0, "commission": 0.65, "ts": 1234567891000, "venue": "binance"},
        src="execution_engine",
        dst="position_tracking",
        rid="RID-chain-2"
    )
    
    # Act: Process both events
    position_tracking_domain.on_trade_executed(trade_event_1)
    position_tracking_domain.on_trade_executed(trade_event_2)
    
    # Assert: WAL entries have correct structure
    wal_file_path = wal._get_wal_file_path()
    with open(wal_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        assert len(lines) >= 2, "WAL should contain at least 2 entries"
        
        # Parse first entry
        entry_1 = json.loads(lines[-2])
        assert "_prev" in entry_1
        assert "_hash" in entry_1
        assert entry_1["rid"] == "RID-chain-1"
        
        # Parse second entry
        entry_2 = json.loads(lines[-1])
        assert "_prev" in entry_2
        assert "_hash" in entry_2
        assert entry_2["rid"] == "RID-chain-2"
        
        # Verify chain integrity: entry_2._prev == entry_1._hash
        assert entry_2["_prev"] == entry_1["_hash"], \
            "WAL chain integrity: second entry must reference first entry's hash"
