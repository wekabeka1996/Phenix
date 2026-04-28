"""
WAL Tailer Tests

Test unified tailing functionality including:
- Reading existing files
- Tailing for new data
- File rotation detection
- State persistence (restart recovery)
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import AsyncMock

from apps.reference.domains.neocortex.config_models import ReplayConfig
from apps.reference.domains.neocortex.logic.ingest.tailer import WalTailer, TailerState


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_wal_dir():
    """Create a temporary WAL directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_state_file():
    """Create a temporary state file path."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def sample_events():
    """Sample FEATURES_CALCULATED events."""
    return [
        {"verb": "FEATURES_CALCULATED", "timestamp": 1000,
            "payload": {"timestamp": 1000, "features": {"a": "1"}}},
        {"verb": "FEATURES_CALCULATED", "timestamp": 1001,
            "payload": {"timestamp": 1001, "features": {"a": "2"}}},
        {"verb": "TRADE_INTENT", "timestamp": 1002, "payload": {
            "symbol": "BTC"}},  # Should be filtered
        {"verb": "FEATURES_CALCULATED", "timestamp": 1003,
            "payload": {"timestamp": 1003, "features": {"a": "3"}}},
    ]


def write_wal_file(path: Path, events: list):
    """Helper to write events to a WAL file."""
    with open(path, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')


# =============================================================================
# HELPER
# =============================================================================

def run_async(coro, timeout=5.0):
    """Run async coroutine with timeout."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(asyncio.wait_for(coro, timeout))
    except asyncio.TimeoutError:
        pass
    finally:
        loop.close()


# =============================================================================
# TESTS
# =============================================================================

def test_tailer_reads_existing_file(temp_wal_dir, temp_state_file, sample_events):
    """Test that tailer reads existing WAL files."""

    # Create WAL file
    wal_file = temp_wal_dir / "wal_001.jsonl"
    write_wal_file(wal_file, sample_events)

    handled_events = []

    async def handler(event):
        handled_events.append(event)

    config = ReplayConfig(
        enabled=True,
        wal_dir=temp_wal_dir,
        batch_size=10,
        poll_interval=0.05,
        max_feature_lines_total_per_cycle=1000,
        max_feature_lines_per_symbol_per_cycle=200,
        max_order_lines_per_cycle=500,
        max_core_lines_per_cycle=500,
        feature_missing_timestamp_policy="fail_closed",
        filter_verb="FEATURES_CALCULATED"
    )

    tailer = WalTailer(
        config=config,
        handler=handler,
        state_path=temp_state_file,
        wal_dir=temp_wal_dir
    )

    async def run_test():
        # Run tailer briefly
        task = asyncio.create_task(tailer.run())
        await asyncio.sleep(0.2)
        tailer.stop()
        await task

    run_async(run_test())

    # Should have read 3 FEATURES_CALCULATED events
    assert len(handled_events) == 3, f"Expected 3, got {len(handled_events)}"
    assert tailer.stats["events_filtered"] == 1  # TRADE_INTENT


def test_tailer_appends_new_data(temp_wal_dir, temp_state_file):
    """Test that tailer picks up new data appended to file."""

    # Create initial WAL file
    wal_file = temp_wal_dir / "wal_001.jsonl"
    write_wal_file(wal_file, [
        {"verb": "FEATURES_CALCULATED", "timestamp": 1000,
            "payload": {"timestamp": 1000}}
    ])

    handled_events = []

    async def handler(event):
        handled_events.append(event)

    config = ReplayConfig(
        enabled=True,
        wal_dir=temp_wal_dir,
        batch_size=10,
        poll_interval=0.05,
        max_feature_lines_total_per_cycle=1000,
        max_feature_lines_per_symbol_per_cycle=200,
        max_order_lines_per_cycle=500,
        max_core_lines_per_cycle=500,
        feature_missing_timestamp_policy="fail_closed",
        filter_verb="FEATURES_CALCULATED"
    )

    tailer = WalTailer(
        config=config,
        handler=handler,
        state_path=temp_state_file,
        wal_dir=temp_wal_dir
    )

    async def run_test():
        task = asyncio.create_task(tailer.run())

        # Wait for initial read
        await asyncio.sleep(0.1)
        initial_count = len(handled_events)

        # Append new data
        with open(wal_file, 'a') as f:
            f.write(json.dumps({"verb": "FEATURES_CALCULATED", "timestamp": 2000, "payload": {
                    "timestamp": 2000}}) + '\n')

        # Wait for tailer to pick it up
        await asyncio.sleep(0.2)

        tailer.stop()
        await task

        return initial_count, len(handled_events)

    initial, final = run_async(run_test())

    assert initial == 1
    assert final == 2, f"Expected 2 events after append, got {final}"


def test_tailer_file_rotation(temp_wal_dir, temp_state_file):
    """Test that tailer detects file rotation and switches to new file."""

    # Create first WAL file
    wal_file1 = temp_wal_dir / "wal_001.jsonl"
    write_wal_file(wal_file1, [
        {"verb": "FEATURES_CALCULATED", "timestamp": 1000,
            "payload": {"timestamp": 1000}}
    ])

    handled_events = []

    async def handler(event):
        handled_events.append(event)

    config = ReplayConfig(
        enabled=True,
        wal_dir=temp_wal_dir,
        batch_size=10,
        poll_interval=0.05,
        max_feature_lines_total_per_cycle=1000,
        max_feature_lines_per_symbol_per_cycle=200,
        max_order_lines_per_cycle=500,
        max_core_lines_per_cycle=500,
        feature_missing_timestamp_policy="fail_closed",
        filter_verb="FEATURES_CALCULATED"
    )

    tailer = WalTailer(
        config=config,
        handler=handler,
        state_path=temp_state_file,
        wal_dir=temp_wal_dir
    )

    async def run_test():
        task = asyncio.create_task(tailer.run())

        await asyncio.sleep(0.1)

        # Create new (rotated) file with newer mtime
        await asyncio.sleep(0.01)  # Ensure different mtime
        wal_file2 = temp_wal_dir / "wal_002.jsonl"
        write_wal_file(wal_file2, [
            {"verb": "FEATURES_CALCULATED", "timestamp": 2000,
                "payload": {"timestamp": 2000}}
        ])

        # Wait for tailer to switch
        await asyncio.sleep(0.3)

        tailer.stop()
        await task

        return len(handled_events)

    count = run_async(run_test())

    # Should have read from both files
    assert count == 2, f"Expected 2 events (from both files), got {count}"


def test_tailer_state_persistence(temp_wal_dir, temp_state_file, sample_events):
    """Test that tailer saves and loads state correctly."""

    # Create WAL file
    wal_file = temp_wal_dir / "wal_001.jsonl"
    write_wal_file(wal_file, sample_events)

    handled_events = []

    async def handler(event):
        handled_events.append(event)

    config = ReplayConfig(
        enabled=True,
        wal_dir=temp_wal_dir,
        batch_size=10,
        poll_interval=0.05,
        max_feature_lines_total_per_cycle=1000,
        max_feature_lines_per_symbol_per_cycle=200,
        max_order_lines_per_cycle=500,
        max_core_lines_per_cycle=500,
        feature_missing_timestamp_policy="fail_closed",
        filter_verb="FEATURES_CALCULATED"
    )

    # First run
    tailer1 = WalTailer(
        config=config,
        handler=handler,
        state_path=temp_state_file,
        wal_dir=temp_wal_dir
    )

    async def first_run():
        task = asyncio.create_task(tailer1.run())
        await asyncio.sleep(0.2)
        tailer1.stop()
        await task

    run_async(first_run())

    first_run_count = len(handled_events)

    # State should be saved
    assert temp_state_file.exists()

    # Second run (simulate restart)
    handled_events.clear()

    tailer2 = WalTailer(
        config=config,
        handler=handler,
        state_path=temp_state_file,
        wal_dir=temp_wal_dir
    )

    async def second_run():
        task = asyncio.create_task(tailer2.run())
        await asyncio.sleep(0.2)
        tailer2.stop()
        await task

    run_async(second_run())

    # Should NOT re-read the same events
    assert len(
        handled_events) == 0, f"Expected 0 on restart, got {len(handled_events)}"
    assert first_run_count == 3


def test_tailer_handles_incomplete_json(temp_wal_dir, temp_state_file):
    """Test graceful handling of incomplete JSON lines."""

    wal_file = temp_wal_dir / "wal_001.jsonl"

    # Write valid line + incomplete line
    with open(wal_file, 'w') as f:
        f.write(
            '{"verb":"FEATURES_CALCULATED","timestamp":1000,"payload":{"timestamp":1000}}\n')
        f.write('{"verb":"FEATURES_CAL')  # Incomplete

    handled_events = []

    async def handler(event):
        handled_events.append(event)

    config = ReplayConfig(
        enabled=True,
        wal_dir=temp_wal_dir,
        batch_size=10,
        poll_interval=0.05,
        max_feature_lines_total_per_cycle=1000,
        max_feature_lines_per_symbol_per_cycle=200,
        max_order_lines_per_cycle=500,
        max_core_lines_per_cycle=500,
        feature_missing_timestamp_policy="fail_closed",
        filter_verb="FEATURES_CALCULATED"
    )

    tailer = WalTailer(
        config=config,
        handler=handler,
        state_path=temp_state_file,
        wal_dir=temp_wal_dir
    )

    async def run_test():
        task = asyncio.create_task(tailer.run())
        await asyncio.sleep(0.2)

        # Now complete the line
        with open(wal_file, 'a') as f:
            f.write(
                'CULATED","timestamp":2000,"payload":{"timestamp":2000}}\n')

        await asyncio.sleep(0.2)
        tailer.stop()
        await task

    run_async(run_test())

    # Should have read both valid events eventually
    assert len(handled_events) >= 1  # At least the first complete one


def test_tailer_stats():
    """Test tailer statistics."""

    config = ReplayConfig(enabled=False)

    tailer = WalTailer(
        config=config,
        handler=AsyncMock(),
        state_path=Path("/tmp/test_state.json"),
        wal_dir=Path("/tmp")
    )

    stats = tailer.stats

    assert "events_processed" in stats
    assert "events_filtered" in stats
    assert "files_processed" in stats
    assert "running" in stats
    assert "tailing" in stats
    assert "offsets" in stats


def test_tailer_disabled():
    """Test disabled tailer does nothing."""

    config = ReplayConfig(enabled=False)

    handled = []

    async def handler(event):
        handled.append(event)

    tailer = WalTailer(
        config=config,
        handler=handler,
        state_path=Path("/tmp/test.json"),
        wal_dir=Path("/tmp")
    )

    run_async(tailer.run())

    assert len(handled) == 0
