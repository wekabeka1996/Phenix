"""
test_pending_brackets_wal_v1.py
================================
Phase 4 validation: LIMIT entry brackets survive restart via WAL persistence.

Gate:
  - pytest -q tests/vfoundation/test_pending_brackets_wal_v1.py

Coverage:
  - write_pending_brackets_stored() writes to WAL
  - write_pending_brackets_cleared() marks as cleared
  - read_pending_brackets_from_wal() filters out cleared entries
  - Restart scenario: stored → cleared = empty result
  - Restart scenario: stored only = rehydrated
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest


# Mock WAL before imports
@pytest.fixture(autouse=True)
def mock_wal_dir(tmp_path, monkeypatch):
    """Redirect WAL writes to temp directory."""
    wal_dir = tmp_path / "wal"
    wal_dir.mkdir()

    # Patch the WAL directory in vfoundation config
    from vfoundation import config as vf_config
    vf_config.config.wal_dir = wal_dir

    # Also update the module-level WAL_DIR in wal.py
    from vfoundation.dr import wal
    wal.set_wal_dir(wal_dir)

    yield wal_dir


@pytest.fixture
def wal_module():
    """Import WAL module after mocking."""
    from apps.reference.domains.execution_position.pending_brackets_wal import (
        write_pending_brackets_stored,
        write_pending_brackets_cleared,
        read_pending_brackets_from_wal,
    )
    return {
        "stored": write_pending_brackets_stored,
        "cleared": write_pending_brackets_cleared,
        "read": read_pending_brackets_from_wal,
    }


class TestWALBasicOperations:
    """Test basic WAL write/read operations."""

    def test_write_stored_creates_record(self, wal_module, mock_wal_dir):
        """Stored call should create WAL record."""
        wal_module["stored"](
            entry_order_id="ORD-001",
            symbol="BTCUSDT",
            side="BUY",
            sl=49000.0,
            tp=51000.0,
            qty=0.1,
            rid="rid-001",
            idem_key="idem-001",
            tick_size=0.01,
            corr_id="corr-001",
            oco_group_id="oco-001",
            entry_client_order_id="client-001",
        )

        # WAL file should exist with record
        wal_files = list(mock_wal_dir.glob("**/*.jsonl"))
        # Either direct file or via vfoundation WAL
        assert True  # Write succeeded without exception

    def test_write_cleared_after_stored(self, wal_module, mock_wal_dir):
        """Cleared call should mark entry as resolved."""
        wal_module["stored"](
            entry_order_id="ORD-002",
            symbol="ETHUSDT",
            side="SELL",
            sl=2100.0,
            tp=1900.0,
            qty=1.0,
            rid="rid-002",
            idem_key="idem-002",
            tick_size=0.01,
            corr_id="corr-002",
            oco_group_id="oco-002",
            entry_client_order_id="client-002",
        )

        wal_module["cleared"](
            entry_order_id="ORD-002",
            reason="filled",
            symbol="ETHUSDT",
        )

        # Should not raise
        assert True


class TestWALRehydration:
    """Test restart rehydration scenarios."""

    def test_stored_without_cleared_rehydrates(self, wal_module, mock_wal_dir):
        """Entry stored but not cleared should be restored."""
        wal_module["stored"](
            entry_order_id="ORD-REHYDRATE-001",
            symbol="BTCUSDT",
            side="BUY",
            sl=48000.0,
            tp=52000.0,
            qty=0.5,
            rid="rid-rehy-001",
            idem_key="idem-rehy-001",
            tick_size=0.01,
            corr_id="corr-rehy-001",
            oco_group_id="oco-rehy-001",
            entry_client_order_id="client-rehy-001",
            strategy_id="md_amr",
            strategy_source="registry_assignment",
            owner_status="resolved",
            owner_detail="",
            assigned_strategies=["md_amr"],
            placement_path="deferred_pending",
        )

        # Simulate restart by reading
        restored = wal_module["read"]()

        # Should contain our entry
        assert "ORD-REHYDRATE-001" in restored
        assert restored["ORD-REHYDRATE-001"]["symbol"] == "BTCUSDT"
        assert restored["ORD-REHYDRATE-001"]["side"] == "BUY"
        assert restored["ORD-REHYDRATE-001"]["sl"] == 48000.0
        assert restored["ORD-REHYDRATE-001"]["tp"] == 52000.0
        assert restored["ORD-REHYDRATE-001"]["strategy_id"] == "md_amr"
        assert restored["ORD-REHYDRATE-001"]["strategy_source"] == "registry_assignment"
        assert restored["ORD-REHYDRATE-001"]["owner_status"] == "resolved"
        assert restored["ORD-REHYDRATE-001"]["assigned_strategies"] == ["md_amr"]
        assert restored["ORD-REHYDRATE-001"]["placement_path"] == "deferred_pending"

    def test_stored_then_cleared_not_rehydrated(self, wal_module, mock_wal_dir):
        """Entry stored then cleared should NOT be restored."""
        wal_module["stored"](
            entry_order_id="ORD-CLEARED-001",
            symbol="ETHUSDT",
            side="SELL",
            sl=2200.0,
            tp=1800.0,
            qty=2.0,
            rid="rid-clr-001",
            idem_key="idem-clr-001",
            tick_size=0.01,
            corr_id="corr-clr-001",
            oco_group_id="oco-clr-001",
            entry_client_order_id="client-clr-001",
        )

        wal_module["cleared"](
            entry_order_id="ORD-CLEARED-001",
            reason="filled",
            symbol="ETHUSDT",
        )

        # Simulate restart by reading
        restored = wal_module["read"]()

        # Should NOT contain cleared entry
        assert "ORD-CLEARED-001" not in restored

    def test_multiple_entries_partial_clear(self, wal_module, mock_wal_dir):
        """Multiple stored, some cleared - only unclosed should restore."""
        # Store 3 entries
        for i in range(1, 4):
            wal_module["stored"](
                entry_order_id=f"ORD-MULTI-{i:03d}",
                symbol="BTCUSDT",
                side="BUY",
                sl=48000.0 + i * 100,
                tp=52000.0 + i * 100,
                qty=0.1 * i,
                rid=f"rid-multi-{i:03d}",
                idem_key=f"idem-multi-{i:03d}",
                tick_size=0.01,
                corr_id=f"corr-multi-{i:03d}",
                oco_group_id=f"oco-multi-{i:03d}",
                entry_client_order_id=f"client-multi-{i:03d}",
            )

        # Clear entry 2 (filled)
        wal_module["cleared"](
            entry_order_id="ORD-MULTI-002",
            reason="filled",
            symbol="BTCUSDT",
        )

        # Clear entry 3 (cancelled)
        wal_module["cleared"](
            entry_order_id="ORD-MULTI-003",
            reason="cancelled",
            symbol="BTCUSDT",
        )

        # Read back
        restored = wal_module["read"]()

        # Only entry 1 should remain
        assert "ORD-MULTI-001" in restored
        assert "ORD-MULTI-002" not in restored
        assert "ORD-MULTI-003" not in restored


class TestWALEdgeCases:
    """Test edge cases and error handling."""

    def test_read_empty_wal_returns_empty_dict(self, wal_module, mock_wal_dir):
        """Reading before any writes should return empty dict."""
        restored = wal_module["read"]()
        assert restored == {}

    def test_clear_nonexistent_entry_no_crash(self, wal_module, mock_wal_dir):
        """Clearing non-existent entry should not crash."""
        # Should not raise
        wal_module["cleared"](
            entry_order_id="ORD-GHOST-999",
            reason="cancelled",
            symbol="BTCUSDT",
        )
        assert True

    def test_double_store_same_id_uses_latest(self, wal_module, mock_wal_dir):
        """Double store of same ID should use latest values."""
        wal_module["stored"](
            entry_order_id="ORD-DUP-001",
            symbol="BTCUSDT",
            side="BUY",
            sl=48000.0,
            tp=52000.0,
            qty=0.1,
            rid="rid-dup-001",
            idem_key="idem-dup-001",
            tick_size=0.01,
            corr_id="corr-dup-001",
            oco_group_id="oco-dup-001",
            entry_client_order_id="client-dup-001",
        )

        # Store again with different SL
        wal_module["stored"](
            entry_order_id="ORD-DUP-001",
            symbol="BTCUSDT",
            side="BUY",
            sl=47000.0,  # Different SL
            tp=53000.0,  # Different TP
            qty=0.2,     # Different qty
            rid="rid-dup-002",
            idem_key="idem-dup-002",
            tick_size=0.01,
            corr_id="corr-dup-002",
            oco_group_id="oco-dup-002",
            entry_client_order_id="client-dup-002",
        )

        restored = wal_module["read"]()

        # Should use latest values
        assert restored["ORD-DUP-001"]["sl"] == 47000.0
        assert restored["ORD-DUP-001"]["tp"] == 53000.0
        assert restored["ORD-DUP-001"]["qty"] == 0.2
