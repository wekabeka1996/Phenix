"""
Test Suite for Disaster Recovery (DR) State Replay

Tests the complete DR cycle:
1. Load snapshot
2. Replay WAL entries after snapshot
3. Verify state consistency

WHY: Validate complete disaster recovery mechanism works correctly [FSMP-RESILIENCE-T04A]
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from vfoundation.dr.dr_loader import find_latest_snapshot, replay_wal_after


class TestDRLoader:
    """Test disaster recovery loader utilities"""

    def test_find_latest_snapshot_empty_directory(self):
        """Should return None when directory is empty"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = find_latest_snapshot(tmpdir)
            assert result is None

    def test_find_latest_snapshot_no_directory(self):
        """Should return None when directory doesn't exist"""
        result = find_latest_snapshot("/nonexistent/path/to/snapshots")
        assert result is None

    def test_find_latest_snapshot_multiple_files(self):
        """Should return the most recently modified snapshot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create multiple snapshot files with different modification times
            old_snapshot = tmppath / "snapshot_old.json"
            old_snapshot.write_text('{"test": "old"}')
            old_snapshot.touch()  # Set mtime to now

            # Sleep to ensure different timestamps
            import time

            time.sleep(0.01)

            new_snapshot = tmppath / "snapshot_new.json"
            new_snapshot.write_text('{"test": "new"}')
            new_snapshot.touch()

            result = find_latest_snapshot(tmpdir)

            assert result is not None
            assert result.name == "snapshot_new.json"

    def test_replay_wal_no_directory(self):
        """Should return 0 when WAL directory doesn't exist"""
        mock_fsm = MagicMock()
        count = replay_wal_after("/nonexistent/wal", "2025-01-01T00:00:00Z", mock_fsm)
        assert count == 0

    def test_replay_wal_invalid_timestamp(self):
        """Should return 0 when timestamp is invalid"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_fsm = MagicMock()
            count = replay_wal_after(tmpdir, "invalid-timestamp", mock_fsm)
            assert count == 0

    def test_replay_wal_empty_directory(self):
        """Should return 0 when WAL directory is empty"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_fsm = MagicMock()
            count = replay_wal_after(tmpdir, "2025-01-01T00:00:00Z", mock_fsm)
            assert count == 0

    def test_replay_wal_with_events(self):
        """Should replay events after snapshot timestamp"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create WAL file with events
            wal_file = tmppath / "2025-10-20.jsonl"

            # Snapshot timestamp: 2025-10-20 10:00:00
            snapshot_ts = datetime(2025, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
            int(snapshot_ts.timestamp() * 1_000_000)

            # Event before snapshot (should be skipped)
            before_ts = int(
                (snapshot_ts - timedelta(minutes=5)).timestamp() * 1_000_000
            )
            event_before = {
                "op": "EVT",
                "verb": "TRADE_EXECUTED",
                "pld": {
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "quantity": 0.1,
                    "price": 50000.0,
                    "commission": 5.0,
                    "ts": before_ts,
                    "venue": "binance",
                },
                "src": "execution_engine",
                "dst": "position_tracking",
                "rid": "RID-before",
                "timestamp": before_ts,
                "_prev": "0" * 64,
                "_hash": "a" * 64,
            }

            # Event after snapshot (should be replayed)
            after_ts = int((snapshot_ts + timedelta(minutes=5)).timestamp() * 1_000_000)
            event_after = {
                "op": "EVT",
                "verb": "TRADE_EXECUTED",
                "pld": {
                    "symbol": "ETHUSDT",
                    "side": "sell",
                    "quantity": 1.0,
                    "price": 3500.0,
                    "commission": 3.5,
                    "ts": after_ts,
                    "venue": "binance",
                },
                "src": "execution_engine",
                "dst": "position_tracking",
                "rid": "RID-after",
                "timestamp": after_ts,
                "_prev": "a" * 64,
                "_hash": "b" * 64,
            }

            # Account update after snapshot
            account_ts = int(
                (snapshot_ts + timedelta(minutes=10)).timestamp() * 1_000_000
            )
            event_account = {
                "op": "EVT",
                "verb": "ACCOUNT_UPDATE_RECEIVED",
                "pld": {
                    "equity": 10500.0,
                    "balance": 10000.0,
                    "margin_used": 500.0,
                    "ts": account_ts,
                    "venue": "binance",
                },
                "src": "account_connector",
                "dst": "position_tracking",
                "rid": "RID-account",
                "timestamp": account_ts,
                "_prev": "b" * 64,
                "_hash": "c" * 64,
            }

            # Write events to WAL file
            with open(wal_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(event_before) + "\n")
                f.write(json.dumps(event_after) + "\n")
                f.write(json.dumps(event_account) + "\n")

            # Create mock FSM with handlers
            mock_fsm = MagicMock()
            mock_fsm.on_trade_executed = MagicMock()
            mock_fsm.on_account_update = MagicMock()

            # Replay WAL
            count = replay_wal_after(tmpdir, snapshot_ts.isoformat(), mock_fsm)

            # Assertions
            assert count == 2, (
                "Should replay 2 events (1 trade + 1 account update after snapshot)"
            )
            assert mock_fsm.on_trade_executed.call_count == 1, (
                "Should call on_trade_executed once"
            )
            assert mock_fsm.on_account_update.call_count == 1, (
                "Should call on_account_update once"
            )

            # Verify correct event was replayed
            trade_call_args = mock_fsm.on_trade_executed.call_args[0][0]
            assert trade_call_args.verb == "TRADE_EXECUTED"
            assert trade_call_args.pld["symbol"] == "ETHUSDT"  # The AFTER event
            assert trade_call_args.rid == "RID-after"

            account_call_args = mock_fsm.on_account_update.call_args[0][0]
            assert account_call_args.verb == "ACCOUNT_UPDATE_RECEIVED"
            assert account_call_args.pld["equity"] == 10500.0

    def test_replay_wal_skips_corrupted_lines(self):
        """Should skip malformed JSON lines and continue replay"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create WAL file with corrupted line
            wal_file = tmppath / "2025-10-20.jsonl"

            snapshot_ts = datetime(2025, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
            after_ts = int((snapshot_ts + timedelta(minutes=5)).timestamp() * 1_000_000)

            valid_event = {
                "op": "EVT",
                "verb": "TRADE_EXECUTED",
                "pld": {
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "quantity": 0.1,
                    "price": 50000.0,
                    "commission": 5.0,
                    "ts": after_ts,
                    "venue": "binance",
                },
                "src": "execution_engine",
                "dst": "position_tracking",
                "rid": "RID-valid",
                "timestamp": after_ts,
                "_prev": "0" * 64,
                "_hash": "a" * 64,
            }

            with open(wal_file, "w", encoding="utf-8") as f:
                f.write("{ CORRUPTED JSON LINE\n")
                f.write(json.dumps(valid_event) + "\n")
                f.write("ANOTHER CORRUPTED LINE\n")

            mock_fsm = MagicMock()
            mock_fsm.on_trade_executed = MagicMock()

            count = replay_wal_after(tmpdir, snapshot_ts.isoformat(), mock_fsm)

            assert count == 1, "Should replay 1 valid event despite corrupted lines"
            assert mock_fsm.on_trade_executed.call_count == 1

    def test_replay_wal_skips_events_without_timestamp(self):
        """Should skip events that don't have timestamp field"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            wal_file = tmppath / "2025-10-20.jsonl"

            snapshot_ts = datetime(2025, 10, 20, 10, 0, 0, tzinfo=timezone.utc)

            # Event without timestamp
            event_no_ts = {
                "op": "EVT",
                "verb": "TRADE_EXECUTED",
                "pld": {"symbol": "BTCUSDT"},
                "src": "execution_engine",
                "dst": "position_tracking",
                "rid": "RID-no-ts",
                "_prev": "0" * 64,
                "_hash": "a" * 64,
            }

            with open(wal_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(event_no_ts) + "\n")

            mock_fsm = MagicMock()
            mock_fsm.on_trade_executed = MagicMock()

            count = replay_wal_after(tmpdir, snapshot_ts.isoformat(), mock_fsm)

            assert count == 0, "Should not replay events without timestamp"
            assert mock_fsm.on_trade_executed.call_count == 0
