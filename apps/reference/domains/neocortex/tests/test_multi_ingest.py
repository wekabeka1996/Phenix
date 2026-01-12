"""
Multi-Source Ingestion Tests

Test parsing and correlation of multiple log sources.
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock

from logic.ingest.parsers import (
    FeatureLogEntry, parse_feature_log_line,
    OrderLogEntry, OrderEventType, parse_order_log_line,
    CoreLogEntry, CoreEventType, parse_core_log_line,
)
from logic.ingest.multi_tailer import MultiTailer, MultiSourceConfig, Episode


# =============================================================================
# PARSER TESTS
# =============================================================================

class TestFeatureParser:
    """Test feature log parsing."""
    
    def test_parse_valid_line(self):
        line = '2026-01-09 12:58:42,585 - apps.reference.domains.feature_engineering.FeatureEngineering - INFO - Calculated features for BTCUSDT: {"obi": "-0.68", "rsi": "45.5", "vol": "0.03"}'
        
        entry = parse_feature_log_line(line)
        
        assert entry is not None
        assert entry.symbol == "BTCUSDT"
        assert entry.features["obi"] == -0.68
        assert entry.features["rsi"] == 45.5
        assert entry.timestamp > 0
    
    def test_parse_invalid_line(self):
        line = "This is not a feature log line"
        entry = parse_feature_log_line(line)
        assert entry is None
    
    def test_parse_empty_line(self):
        entry = parse_feature_log_line("")
        assert entry is None


class TestOrderParser:
    """Test order log parsing."""
    
    def test_parse_order_placed(self):
        line = '{"event_type": "ORDER_PLACED", "symbol": "BTCUSDT", "side": "BUY", "quantity": 0.5, "order_id": "12345", "timestamp": 1736380000.0, "metadata": {"order_type": "MARKET_ENTRY"}}'
        
        entry = parse_order_log_line(line)
        
        assert entry is not None
        assert entry.event_type == OrderEventType.PLACED
        assert entry.symbol == "BTCUSDT"
        assert entry.side == "BUY"
        assert entry.quantity == 0.5
        assert entry.is_entry is True
    
    def test_parse_order_rejected(self):
        line = '{"event_type": "ORDER_REJECTED", "symbol": "ETHUSDT", "side": "SELL", "nrr_code": "NRR-027", "why": "downtrend blocks long", "timestamp": 1736380000.0}'
        
        entry = parse_order_log_line(line)
        
        assert entry is not None
        assert entry.event_type == OrderEventType.REJECTED
        assert entry.nrr_code == "NRR-027"
    
    def test_parse_invalid_json(self):
        entry = parse_order_log_line("not json")
        assert entry is None


class TestCoreParser:
    """Test core log parsing."""
    
    def test_parse_position_closed(self):
        line = "2026-01-09 12:19:31,887 - aurora_handler.aurora - INFO - [BTCUSDT] Position closed (neutral). Starting re-entry cooldown."
        
        entry = parse_core_log_line(line)
        
        assert entry is not None
        assert entry.event_type == CoreEventType.POSITION_CLOSED
        assert entry.symbol == "BTCUSDT"
        assert entry.reason == "neutral"
    
    def test_parse_equity_update(self):
        line = "2026-01-09 12:19:29,044 - apps.reference.domains.account_balance.account_connector - INFO - Emitted positions update: 2 open positions, totalWalletBalance=293.27235042, totalUnrealizedProfit=0E-8"
        
        entry = parse_core_log_line(line)
        
        assert entry is not None
        assert entry.event_type == CoreEventType.EQUITY_UPDATE
        assert entry.equity == 293.27235042
        assert entry.unrealized_pnl == 0.0
    
    def test_parse_irrelevant_line(self):
        line = "2026-01-09 12:19:31,397 - order_guardian - INFO - [GUARD] Linked existing orders from REST"
        entry = parse_core_log_line(line)
        # This line doesn't match our patterns
        assert entry is None


# =============================================================================
# MULTI-TAILER TESTS
# =============================================================================

def run_async(coro, timeout=5.0):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(asyncio.wait_for(coro, timeout))
    except asyncio.TimeoutError:
        pass
    finally:
        loop.close()


class TestMultiTailer:
    """Test multi-source tailer integration."""
    
    @pytest.fixture
    def temp_logs(self):
        """Create temporary log structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create features directory
            features_dir = tmpdir / "features"
            features_dir.mkdir()
            
            # Create BTCUSDT.log
            btc_log = features_dir / "BTCUSDT.log"
            btc_log.write_text(
                "2026-01-09 12:00:00,000 - feature_engineering.FeatureEngineering - INFO - "
                'Calculated features for BTCUSDT: {"obi": "0.5", "rsi": "50.0", "vol": "0.02"}\n'
                "2026-01-09 12:00:01,000 - feature_engineering.FeatureEngineering - INFO - "
                'Calculated features for BTCUSDT: {"obi": "0.6", "rsi": "52.0", "vol": "0.03"}\n'
            )
            
            # Create orders file
            orders_file = tmpdir / "order_log.jsonl"
            orders_file.write_text(
                '{"event_type": "ORDER_PLACED", "symbol": "BTCUSDT", "side": "BUY", '
                '"quantity": 0.5, "timestamp": 1736380001.0, "metadata": {"order_type": "MARKET_ENTRY"}}\n'
            )
            
            # Create core log
            core_log = tmpdir / "aurora_core.log"
            core_log.write_text(
                "2026-01-09 12:00:02,000 - aurora_handler.aurora - INFO - "
                "[BTCUSDT] Position closed (neutral). Starting re-entry cooldown.\n"
            )
            
            yield {
                "root": tmpdir,
                "features_dir": features_dir,
                "orders_file": orders_file,
                "core_log": core_log
            }
    
    def test_tailer_reads_features(self, temp_logs):
        """Test that tailer reads feature files."""
        
        features_received = []
        
        async def handler(event):
            features_received.append(event)
        
        config = MultiSourceConfig(
            enabled=True,
            features_dir=temp_logs["features_dir"],
            orders_file=temp_logs["orders_file"],
            core_log=temp_logs["core_log"],
            symbols=["BTCUSDT"],
            batch_size=10
        )
        
        tailer = MultiTailer(
            config=config,
            feature_handler=handler,
            state_path=temp_logs["root"] / "state.json"
        )
        
        async def run_test():
            task = asyncio.create_task(tailer.run())
            await asyncio.sleep(0.3)
            tailer.stop()
            await task
        
        run_async(run_test())
        
        assert len(features_received) == 2
        assert features_received[0]["symbol"] == "BTCUSDT"
    
    def test_tailer_reads_orders(self, temp_logs):
        """Test that tailer reads order log."""
        
        config = MultiSourceConfig(
            enabled=True,
            features_dir=temp_logs["features_dir"],
            orders_file=temp_logs["orders_file"],
            core_log=temp_logs["core_log"],
            symbols=["BTCUSDT"]
        )
        
        tailer = MultiTailer(
            config=config,
            feature_handler=AsyncMock(),
            state_path=temp_logs["root"] / "state.json"
        )
        
        async def run_test():
            task = asyncio.create_task(tailer.run())
            await asyncio.sleep(0.3)
            tailer.stop()
            await task
        
        run_async(run_test())
        
        assert tailer.stats["orders_processed"] >= 1
    
    def test_tailer_state_persistence(self, temp_logs):
        """Test that tailer saves and loads state."""
        
        config = MultiSourceConfig(
            enabled=True,
            features_dir=temp_logs["features_dir"],
            orders_file=temp_logs["orders_file"],
            core_log=temp_logs["core_log"],
            symbols=["BTCUSDT"]
        )
        
        state_path = temp_logs["root"] / "state.json"
        
        # First run
        tailer1 = MultiTailer(
            config=config,
            feature_handler=AsyncMock(),
            state_path=state_path
        )
        
        async def first_run():
            task = asyncio.create_task(tailer1.run())
            await asyncio.sleep(0.3)
            tailer1.stop()
            await task
        
        run_async(first_run())
        first_features = tailer1.stats["features_processed"]
        
        # State should be saved
        assert state_path.exists()
        
        # Second run
        tailer2 = MultiTailer(
            config=config,
            feature_handler=AsyncMock(),
            state_path=state_path
        )
        
        async def second_run():
            task = asyncio.create_task(tailer2.run())
            await asyncio.sleep(0.3)
            tailer2.stop()
            await task
        
        run_async(second_run())
        
        # Should NOT re-process
        assert tailer2.stats["features_processed"] == 0
    
    def test_tailer_disabled(self):
        """Test disabled tailer does nothing."""
        
        config = MultiSourceConfig(enabled=False)
        
        tailer = MultiTailer(
            config=config,
            feature_handler=AsyncMock()
        )
        
        run_async(tailer.run())
        
        assert tailer.stats["features_processed"] == 0


# =============================================================================
# EPISODE CORRELATION TESTS
# =============================================================================

class TestEpisodeCorrelation:
    """Test that episodes correctly correlate state, action, reward."""
    
    def test_episode_creation(self):
        """Test episode dataclass."""
        episode = Episode(
            symbol="BTCUSDT",
            timestamp=1736380000.0,
            features={"obi": 0.5, "rsi": 50.0},
            side="BUY",
            quantity=0.5,
            order_type="ENTRY",
            rejected=False
        )
        
        assert episode.symbol == "BTCUSDT"
        assert episode.features["obi"] == 0.5
        assert episode.side == "BUY"
        assert episode.reward == 0.0  # Default
