"""
WAL Replayer Tests (Legacy)

Test historical data replay functionality.
NOTE: WalTailer is the preferred implementation. This tests the legacy WALReplayer.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from apps.reference.domains.neocortex.config_models import ReplayConfig
from apps.reference.domains.neocortex.logic.ingest.wal_replayer import WALReplayer


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_wal_content():
    """Sample WAL content with mixed events."""
    return """{"verb":"FEATURES_CALCULATED","timestamp":1000.0,"payload":{"timestamp":1000.0,"symbol":"BTCUSDT","features":{"rsi":"45","obi":"0.1","vol":"0.03"}}}
{"verb":"FEATURES_CALCULATED","timestamp":1001.0,"payload":{"timestamp":1001.0,"symbol":"ETHUSDT","features":{"rsi":"50","obi":"0.2","vol":"0.02"}}}
{"verb":"TRADE_INTENT_PROPOSED","timestamp":1002.0,"payload":{"symbol":"BTCUSDT"}}
{"verb":"FEATURES_CALCULATED","timestamp":1003.0,"payload":{"timestamp":1003.0,"symbol":"BTCUSDT","features":{"rsi":"48","obi":"0.15","vol":"0.04"}}}
{"verb":"POSITION_CLOSED","timestamp":1004.0,"payload":{"symbol":"BTCUSDT"}}
{"verb":"FEATURES_CALCULATED","timestamp":1005.0,"payload":{"timestamp":1005.0,"symbol":"SOLUSDT","features":{"rsi":"55","obi":"-0.1","vol":"0.05"}}}
"""


@pytest.fixture
def temp_wal_file(sample_wal_content):
    """Create a temporary WAL file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write(sample_wal_content)
        return Path(f.name)


@pytest.fixture
def temp_wal_dir(sample_wal_content):
    """Create a temporary directory with WAL files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two WAL files
        file1 = Path(tmpdir) / "wal_001.jsonl"
        file2 = Path(tmpdir) / "wal_002.jsonl"
        
        file1.write_text(sample_wal_content)
        file2.write_text(sample_wal_content)
        
        yield Path(tmpdir)


# =============================================================================
# HELPER
# =============================================================================

def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# TESTS
# =============================================================================

def test_replayer_filters_events(temp_wal_file):
    """Test that replayer filters events by verb."""
    
    handled_events = []
    
    async def mock_handler(event):
        handled_events.append(event)
    
    config = ReplayConfig(
        enabled=True,
        wal_glob=str(temp_wal_file),
        batch_size=10,
        filter_verb="FEATURES_CALCULATED"
    )
    
    replayer = WALReplayer(
        config=config,
        handler=mock_handler,
        base_path=Path("/")  # Absolute path in glob
    )
    
    run_async(replayer.run())
    
    # Should have 4 FEATURES_CALCULATED events (not TRADE_INTENT or POSITION_CLOSED)
    assert len(handled_events) == 4, f"Expected 4 events, got {len(handled_events)}"
    assert replayer.stats["events_replayed"] == 4
    assert replayer.stats["events_filtered"] == 2  # TRADE + POSITION
    assert replayer.stats["completed"] is True


def test_replayer_processes_multiple_files(temp_wal_dir):
    """Test that replayer processes all files in directory."""
    
    handled_count = [0]
    
    async def mock_handler(event):
        handled_count[0] += 1
    
    config = ReplayConfig(
        enabled=True,
        wal_glob=str(temp_wal_dir / "*.jsonl"),
        batch_size=10,
        filter_verb="FEATURES_CALCULATED"
    )
    
    replayer = WALReplayer(
        config=config,
        handler=mock_handler,
        base_path=Path("/")
    )
    
    run_async(replayer.run())
    
    # 4 events per file * 2 files = 8
    assert handled_count[0] == 8
    assert replayer.stats["files_processed"] == 2


def test_replayer_disabled():
    """Test that disabled replayer does nothing."""
    
    handled_events = []
    
    async def mock_handler(event):
        handled_events.append(event)
    
    config = ReplayConfig(
        enabled=False,
        wal_glob="*.jsonl"
    )
    
    replayer = WALReplayer(
        config=config,
        handler=mock_handler
    )
    
    run_async(replayer.run())
    
    assert len(handled_events) == 0
    assert replayer.stats["completed"] is False  # Didn't really run


def test_replayer_no_files_found():
    """Test graceful handling when no WAL files match pattern."""
    
    config = ReplayConfig(
        enabled=True,
        wal_glob="/nonexistent/path/*.jsonl",
        batch_size=10
    )
    
    replayer = WALReplayer(
        config=config,
        handler=AsyncMock()
    )
    
    # Should not crash
    run_async(replayer.run())
    
    assert replayer.stats["files_processed"] == 0
    assert replayer.stats["completed"] is True


def test_replayer_stop():
    """Test that stop() sets the running flag."""
    
    config = ReplayConfig(
        enabled=True,
        wal_glob="/tmp/fake/*.jsonl",
        batch_size=5
    )
    
    replayer = WALReplayer(
        config=config,
        handler=AsyncMock(),
        base_path=Path("/")
    )
    
    # Verify stop() sets the flag
    assert replayer.stats["running"] is False
    replayer._running = True
    replayer.stop()
    assert replayer.stats["running"] is False


def test_replayer_stats():
    """Test stats property."""
    
    config = ReplayConfig(
        enabled=True,
        wal_glob="*.jsonl"
    )
    
    replayer = WALReplayer(
        config=config,
        handler=AsyncMock()
    )
    
    stats = replayer.stats
    
    assert "files_processed" in stats
    assert "events_replayed" in stats
    assert "events_filtered" in stats
    assert "running" in stats
    assert "completed" in stats

