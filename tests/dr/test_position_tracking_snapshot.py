"""
Test suite for PositionTracking.get_snapshot() DR functionality.

Validates that snapshots are schema-compliant and preserve Decimal precision.
"""

import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, List, Callable

import pytest

# Add project root to path for proper imports
project_root = Path(__file__).parents[2]
sys.path.insert(0, str(project_root))

from reference.domains.position_tracking.position_tracking import PositionTracking
from vfoundation.core.protocol import Message


class MockFSMCore:
    """A mock FSMCore for testing purposes."""

    def __init__(self) -> None:
        self.listeners: Dict[str, List[Callable[[Any], None]]] = {}
        self.emitted_events: List[Message] = []

    def listen(self, event_name: str, callback: Callable[[Any], None]) -> None:
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name: str, payload: Dict[str, Any], why: str) -> None:
        message = Message(
            op="EVT",
            verb=event_name.split(":")[1],
            src="test",
            dst="any",
            pld=payload,
            why=why,
        )
        self.emitted_events.append(message)
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                callback(message)


class TestPositionTrackingSnapshot:
    """Test snapshot generation for disaster recovery."""

    @pytest.fixture
    def fsm(self):
        """Create FSM core instance."""
        return MockFSMCore()

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return {"system": {"worker_id": "test-worker-001"}}

    @pytest.fixture
    def position_tracking(self, fsm, config):
        """Create PositionTracking instance."""
        return PositionTracking(fsm, config)

    def test_snapshot_has_required_fields(self, position_tracking):
        """Verify snapshot contains all required schema fields."""
        snapshot = position_tracking.get_snapshot()

        # Top-level required fields
        assert "domain" in snapshot
        assert "version" in snapshot
        assert "timestamp_utc" in snapshot
        assert "state_hash" in snapshot
        assert "state" in snapshot
        assert "metadata" in snapshot

        # Verify domain
        assert snapshot["domain"] == "position_tracking"
        assert snapshot["version"] == "1.0.0"

    def test_snapshot_state_hash_format(self, position_tracking):
        """Verify state_hash follows SHA-256 format."""
        snapshot = position_tracking.get_snapshot()

        state_hash = snapshot["state_hash"]
        # Should be "sha256:<64 hex chars>"
        assert re.match(r"^sha256:[a-f0-9]{64}$", state_hash), (
            f"Invalid hash format: {state_hash}"
        )

    def test_snapshot_state_structure(self, position_tracking):
        """Verify state object has correct structure."""
        snapshot = position_tracking.get_snapshot()

        state = snapshot["state"]
        assert "positions" in state
        assert "portfolio" in state

        # Portfolio required fields
        portfolio = state["portfolio"]
        assert "equity" in portfolio
        assert "balance" in portfolio

    def test_snapshot_metadata_fields(self, position_tracking):
        """Verify metadata contains required fields."""
        snapshot = position_tracking.get_snapshot()

        metadata = snapshot["metadata"]
        assert "worker_id" in metadata
        assert "positions_count" in metadata
        assert "sequence_number" in metadata

        assert metadata["worker_id"] == "test-worker-001"
        assert isinstance(metadata["positions_count"], int)
        assert isinstance(metadata["sequence_number"], int)

    def test_snapshot_preserves_decimal_precision(self, position_tracking):
        """Verify Decimal values are stored as strings with full precision."""
        # Set equity to high-precision value
        position_tracking._equity = Decimal("5003.26150779123456")

        # Add position with high precision
        position_tracking._positions["ETHUSDT"] = {
            "quantity": Decimal("1.234567890123456789"),
            "avg_price": Decimal("3874.115"),
            "venues": ["binance"],
        }

        snapshot = position_tracking.get_snapshot()

        # Check portfolio equity is string
        equity = snapshot["state"]["portfolio"]["equity"]
        assert isinstance(equity, str), f"Equity should be str, got {type(equity)}"
        assert "5003.26150779123456" in equity

        # Check position qty is string with precision
        positions = snapshot["state"]["positions"]
        assert "ETHUSDT" in positions
        eth_pos = positions["ETHUSDT"]
        assert isinstance(eth_pos["qty"], str)
        assert isinstance(eth_pos["avg_price"], str)
        assert "1.234567890123456789" in eth_pos["qty"]
        assert "3874.115" in eth_pos["avg_price"]

    def test_snapshot_hash_changes_with_state(self, position_tracking):
        """Verify state_hash changes when state changes."""
        snapshot1 = position_tracking.get_snapshot()
        hash1 = snapshot1["state_hash"]

        # Modify state
        position_tracking._equity = Decimal("6000.0")

        snapshot2 = position_tracking.get_snapshot()
        hash2 = snapshot2["state_hash"]

        assert hash1 != hash2, "Hash should change when state changes"

    def test_snapshot_includes_all_positions(self, position_tracking):
        """Verify all non-zero positions are included in snapshot."""
        # Add multiple positions
        position_tracking._positions["ETHUSDT"] = {
            "quantity": Decimal("1.5"),
            "avg_price": Decimal("3800.0"),
            "venues": ["binance"],
        }
        position_tracking._positions["BTCUSDT"] = {
            "quantity": Decimal("-0.05"),
            "avg_price": Decimal("67000.0"),
            "venues": ["binance"],
        }
        # Add near-zero position (should be excluded)
        position_tracking._positions["SOLUSDT"] = {
            "quantity": Decimal("0.0000000001"),
            "avg_price": Decimal("100.0"),
            "venues": ["binance"],
        }

        snapshot = position_tracking.get_snapshot()
        positions = snapshot["state"]["positions"]

        assert "ETHUSDT" in positions
        assert "BTCUSDT" in positions
        assert "SOLUSDT" not in positions  # Too small, filtered out
        assert snapshot["metadata"]["positions_count"] == 2

    def test_snapshot_position_side_detection(self, position_tracking):
        """Verify position side (long/short) is correctly detected."""
        position_tracking._positions["ETHUSDT"] = {
            "quantity": Decimal("1.5"),  # Positive = long
            "avg_price": Decimal("3800.0"),
            "venues": ["binance"],
        }
        position_tracking._positions["BTCUSDT"] = {
            "quantity": Decimal("-0.05"),  # Negative = short
            "avg_price": Decimal("67000.0"),
            "venues": ["binance"],
        }

        snapshot = position_tracking.get_snapshot()
        positions = snapshot["state"]["positions"]

        assert positions["ETHUSDT"]["side"] == "long"
        assert positions["BTCUSDT"]["side"] == "short"

    def test_snapshot_is_json_serializable(self, position_tracking):
        """Verify snapshot can be serialized to JSON."""
        position_tracking._equity = Decimal("5000.0")
        position_tracking._positions["ETHUSDT"] = {
            "quantity": Decimal("1.5"),
            "avg_price": Decimal("3800.0"),
            "venues": ["binance"],
        }

        snapshot = position_tracking.get_snapshot()

        # Should not raise exception
        json_str = json.dumps(snapshot, indent=2)
        assert len(json_str) > 0

        # Should be deserializable
        recovered = json.loads(json_str)
        assert recovered["domain"] == "position_tracking"
        assert recovered["state"]["portfolio"]["equity"] == "5000.0"

    def test_snapshot_empty_positions(self, position_tracking):
        """Verify snapshot handles empty positions gracefully."""
        position_tracking._equity = Decimal("5000.0")
        # No positions

        snapshot = position_tracking.get_snapshot()

        assert snapshot["metadata"]["positions_count"] == 0
        assert len(snapshot["state"]["positions"]) == 0
        assert "equity" in snapshot["state"]["portfolio"]


class TestPositionTrackingSnapshotRestore:
    """Test snapshot restoration (load_snapshot) for disaster recovery."""

    @pytest.fixture
    def fsm(self):
        """Create FSM core instance."""
        return MockFSMCore()

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return {"system": {"worker_id": "test-worker-restore"}}

    @pytest.fixture
    def position_tracking(self, fsm, config):
        """Create PositionTracking instance."""
        return PositionTracking(fsm, config)

    def test_load_snapshot_success(self, position_tracking):
        """Verify successful snapshot loading with valid data."""
        # Create a valid snapshot manually
        snapshot_data = {
            "domain": "position_tracking",
            "version": "1.0.0",
            "timestamp_utc": "2025-10-18T12:00:00Z",
            "state": {
                "positions": {
                    "ETHUSDT": {
                        "qty": "1.234567890123456789",
                        "avg_price": "3800.5",
                        "side": "long",
                        "unrealized_pnl": "0.0",
                        "venues": ["binance"],
                    },
                    "BTCUSDT": {
                        "qty": "-0.05",
                        "avg_price": "67000.0",
                        "side": "short",
                        "unrealized_pnl": "0.0",
                        "venues": ["binance"],
                    },
                },
                "portfolio": {
                    "equity": "5000.123456789",
                    "balance": "4900.0",
                    "margin_used": "0.0",
                },
            },
            "metadata": {
                "worker_id": "test-worker-001",
                "positions_count": 2,
                "sequence_number": 1729252800000,
            },
        }

        # Compute valid hash
        import hashlib

        state_str = json.dumps(snapshot_data["state"], sort_keys=True)
        state_hash = hashlib.sha256(state_str.encode("utf-8")).hexdigest()
        snapshot_data["state_hash"] = f"sha256:{state_hash}"

        # Load snapshot
        result = position_tracking.load_snapshot(snapshot_data)

        assert result is True, "load_snapshot should return True on success"

        # Verify positions were restored
        assert len(position_tracking._positions) == 2
        assert "ETHUSDT" in position_tracking._positions
        assert "BTCUSDT" in position_tracking._positions

        # Verify Decimal precision preserved
        eth_pos = position_tracking._positions["ETHUSDT"]
        assert eth_pos["quantity"] == Decimal("1.234567890123456789")
        assert eth_pos["avg_price"] == Decimal("3800.5")

        btc_pos = position_tracking._positions["BTCUSDT"]
        assert btc_pos["quantity"] == Decimal("-0.05")
        assert btc_pos["avg_price"] == Decimal("67000.0")

        # Verify equity restored
        assert position_tracking._equity == Decimal("5000.123456789")

        # Verify realized pnl computed from equity - balance
        assert position_tracking._realized_pnl == Decimal("100.123456789")

    def test_load_snapshot_hash_mismatch(self, position_tracking):
        """Verify load_snapshot fails when hash doesn't match."""
        snapshot_data = {
            "domain": "position_tracking",
            "version": "1.0.0",
            "timestamp_utc": "2025-10-18T12:00:00Z",
            "state": {
                "positions": {},
                "portfolio": {
                    "equity": "5000.0",
                    "balance": "5000.0",
                    "margin_used": "0.0",
                },
            },
            "state_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",  # Invalid hash
            "metadata": {
                "worker_id": "test-worker-001",
                "positions_count": 0,
                "sequence_number": 1729252800000,
            },
        }

        result = position_tracking.load_snapshot(snapshot_data)

        assert result is False, "load_snapshot should return False on hash mismatch"
        # State should remain unchanged (empty)
        assert len(position_tracking._positions) == 0

    def test_load_snapshot_invalid_numeric_value(self, position_tracking):
        """Verify load_snapshot fails with invalid numeric strings."""
        snapshot_data = {
            "domain": "position_tracking",
            "version": "1.0.0",
            "timestamp_utc": "2025-10-18T12:00:00Z",
            "state": {
                "positions": {
                    "ETHUSDT": {
                        "qty": "not_a_number",  # Invalid
                        "avg_price": "3800.0",
                        "side": "long",
                        "unrealized_pnl": "0.0",
                        "venues": ["binance"],
                    }
                },
                "portfolio": {
                    "equity": "5000.0",
                    "balance": "5000.0",
                    "margin_used": "0.0",
                },
            },
            "metadata": {
                "worker_id": "test-worker-001",
                "positions_count": 1,
                "sequence_number": 1729252800000,
            },
        }

        # Compute valid hash for the invalid data
        import hashlib

        state_str = json.dumps(snapshot_data["state"], sort_keys=True)
        state_hash = hashlib.sha256(state_str.encode("utf-8")).hexdigest()
        snapshot_data["state_hash"] = f"sha256:{state_hash}"

        result = position_tracking.load_snapshot(snapshot_data)

        assert result is False, "load_snapshot should return False on invalid numeric"
        # State should remain unchanged
        assert len(position_tracking._positions) == 0

    def test_load_snapshot_missing_required_field(self, position_tracking):
        """Verify load_snapshot fails when required fields are missing."""
        snapshot_data = {
            "domain": "position_tracking",
            "version": "1.0.0",
            # Missing 'state' field
            "timestamp_utc": "2025-10-18T12:00:00Z",
            "state_hash": "sha256:abc123",
            "metadata": {},
        }

        result = position_tracking.load_snapshot(snapshot_data)

        assert result is False, "load_snapshot should return False on missing field"

    def test_load_snapshot_roundtrip(self, position_tracking):
        """Verify get_snapshot() -> load_snapshot() roundtrip preserves state."""
        # Setup initial state
        position_tracking._equity = Decimal("5000.123456789")
        position_tracking._realized_pnl = Decimal("100.5")
        position_tracking._positions["ETHUSDT"] = {
            "quantity": Decimal("1.234567890123456789"),
            "avg_price": Decimal("3800.5"),
            "venues": ["binance"],
        }

        # Create snapshot
        snapshot = position_tracking.get_snapshot()

        # Create new instance
        fsm2 = MockFSMCore()
        pt2 = PositionTracking(fsm2, {"system": {"worker_id": "test2"}})

        # Load snapshot into new instance
        result = pt2.load_snapshot(snapshot)

        assert result is True, "Roundtrip load should succeed"

        # Verify state matches
        assert pt2._equity == position_tracking._equity
        assert len(pt2._positions) == len(position_tracking._positions)
        assert "ETHUSDT" in pt2._positions
        assert pt2._positions["ETHUSDT"]["quantity"] == Decimal("1.234567890123456789")
        assert pt2._positions["ETHUSDT"]["avg_price"] == Decimal("3800.5")

    def test_load_snapshot_overwrites_existing_state(self, position_tracking):
        """Verify load_snapshot overwrites any existing state."""
        # Set initial state
        position_tracking._equity = Decimal("1000.0")
        position_tracking._positions["SOLUSDT"] = {
            "quantity": Decimal("10.0"),
            "avg_price": Decimal("100.0"),
            "venues": ["binance"],
        }

        # Create snapshot with different state
        snapshot_data = {
            "domain": "position_tracking",
            "version": "1.0.0",
            "timestamp_utc": "2025-10-18T12:00:00Z",
            "state": {
                "positions": {
                    "ETHUSDT": {
                        "qty": "5.0",
                        "avg_price": "3800.0",
                        "side": "long",
                        "unrealized_pnl": "0.0",
                        "venues": ["binance"],
                    }
                },
                "portfolio": {
                    "equity": "9000.0",
                    "balance": "8900.0",
                    "margin_used": "0.0",
                },
            },
            "metadata": {
                "worker_id": "test-worker-001",
                "positions_count": 1,
                "sequence_number": 1729252800000,
            },
        }

        # Compute valid hash
        import hashlib

        state_str = json.dumps(snapshot_data["state"], sort_keys=True)
        state_hash = hashlib.sha256(state_str.encode("utf-8")).hexdigest()
        snapshot_data["state_hash"] = f"sha256:{state_hash}"

        # Load snapshot
        result = position_tracking.load_snapshot(snapshot_data)

        assert result is True
        # Old state should be completely replaced
        assert "SOLUSDT" not in position_tracking._positions
        assert "ETHUSDT" in position_tracking._positions
        assert position_tracking._equity == Decimal("9000.0")
        assert position_tracking._realized_pnl == Decimal("100.0")  # 9000 - 8900
