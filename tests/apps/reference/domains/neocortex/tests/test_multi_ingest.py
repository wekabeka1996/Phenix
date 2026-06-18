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

from apps.reference.domains.neocortex.logic.ingest.parsers import (
    FeatureLogEntry, parse_feature_log_line,
    OrderLogEntry, OrderEventType, parse_order_log_line,
    CoreLogEntry, CoreEventType, parse_core_log_line,
)
from apps.reference.domains.neocortex.logic.ingest.multi_tailer import MultiTailer, MultiSourceConfig, Episode


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
        assert entry.event_ts_ms == 1767952722585
        assert entry.timestamp == pytest.approx(entry.event_ts_ms / 1000.0)
    
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
        assert entry.event_ts_ms == 1736380000000
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
        assert entry.event_ts_ms == 1767950371887
    
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

    def test_tailer_drains_rotated_order_log_then_reads_new_active(self, tmp_path):
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        orders_file = tmp_path / "order_log_v1.jsonl"
        core_log = tmp_path / "aurora_core.log"
        core_log.write_text("", encoding="utf-8")

        def order_row(order_id: str, timestamp: int) -> str:
            return json.dumps({
                "event_type": "ORDER_PLACED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.001,
                "order_id": order_id,
                "timestamp": timestamp,
                "metadata": {"order_type": "LIMIT_ENTRY"},
            })

        orders_file.write_text(
            order_row("old-1", 1_700_000_000_000) + "\n"
            + order_row("old-2", 1_700_000_001_000) + "\n",
            encoding="utf-8",
        )
        tailer = MultiTailer(
            config=MultiSourceConfig(
                enabled=True,
                features_dir=features_dir,
                orders_file=orders_file,
                core_log=core_log,
                symbols=["BTCUSDT"],
                max_order_lines_per_cycle=1,
            ),
            feature_handler=AsyncMock(),
            state_path=tmp_path / "state.json",
        )

        async def run_test():
            await tailer._process_orders()
            rotated = tmp_path / "order_log_v1.20260613T100000Z.000.jsonl"
            orders_file.replace(rotated)
            orders_file.write_text(
                order_row("new-1", 1_700_000_002_000) + "\n",
                encoding="utf-8",
            )
            await tailer._process_orders()
            await tailer._process_orders()

        run_async(run_test())

        assert tailer.stats["orders_processed"] == 3

    def test_tailer_restores_rotation_identity_across_restart(self, tmp_path):
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        orders_file = tmp_path / "order_log_v1.jsonl"
        core_log = tmp_path / "aurora_core.log"
        core_log.write_text("", encoding="utf-8")
        state_path = tmp_path / "state.json"

        def order_row(order_id: str, timestamp: int) -> str:
            return json.dumps({
                "event_type": "ORDER_PLACED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.001,
                "order_id": order_id,
                "timestamp": timestamp,
                "metadata": {"order_type": "LIMIT_ENTRY"},
            })

        orders_file.write_text(
            order_row("old-1", 1_700_000_000_000) + "\n"
            + order_row("old-2", 1_700_000_001_000) + "\n",
            encoding="utf-8",
        )
        config = MultiSourceConfig(
            enabled=True,
            features_dir=features_dir,
            orders_file=orders_file,
            core_log=core_log,
            symbols=["BTCUSDT"],
            max_order_lines_per_cycle=1,
        )

        first = MultiTailer(
            config=config, feature_handler=AsyncMock(), state_path=state_path)

        async def first_run():
            await first._process_orders()
            await first.save_state()

        run_async(first_run())
        rotated = tmp_path / "order_log_v1.20260614T100000Z.000.jsonl"
        orders_file.replace(rotated)
        orders_file.write_text(
            order_row("new-1", 1_700_000_002_000) + "\n", encoding="utf-8")

        second = MultiTailer(
            config=config, feature_handler=AsyncMock(), state_path=state_path)

        async def second_run():
            assert await second.load_state() is True
            await second._process_orders()
            await second._process_orders()

        run_async(second_run())

        assert second.stats["orders_processed"] == 2

    def test_tailer_drains_all_pending_rotations_before_active_log(self, tmp_path):
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        orders_file = tmp_path / "order_log_v1.jsonl"
        core_log = tmp_path / "aurora_core.log"
        core_log.write_text("", encoding="utf-8")

        def order_row(order_id: str, timestamp: int) -> str:
            return json.dumps({
                "event_type": "ORDER_PLACED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.001,
                "order_id": order_id,
                "timestamp": timestamp,
                "metadata": {"order_type": "LIMIT_ENTRY"},
            }) + "\n"

        first_rotation = tmp_path / "order_log_v1.20260614T100000Z.000.jsonl"
        second_rotation = tmp_path / "order_log_v1.20260614T110000Z.000.jsonl"
        first_rotation.write_text(order_row("old-1", 1_700_000_000_000), encoding="utf-8")
        second_rotation.write_text(order_row("old-2", 1_700_000_001_000), encoding="utf-8")
        orders_file.write_text(order_row("new-1", 1_700_000_002_000), encoding="utf-8")

        tailer = MultiTailer(
            config=MultiSourceConfig(
                enabled=True,
                features_dir=features_dir,
                orders_file=orders_file,
                core_log=core_log,
                symbols=["BTCUSDT"],
                max_order_lines_per_cycle=2,
            ),
            feature_handler=AsyncMock(),
            state_path=tmp_path / "state.json",
        )
        tailer._order_file_identity = (
            int(orders_file.stat().st_dev), int(orders_file.stat().st_ino))
        tailer._pending_order_rotations = [first_rotation, second_rotation]
        observed: list[str] = []

        async def capture(order):
            observed.append(str(order.order_id))

        tailer._handle_order_event = capture

        async def run_test():
            await tailer._process_orders()
            assert observed == ["old-1", "old-2"]
            await tailer._process_orders()

        run_async(run_test())
        assert observed == ["old-1", "old-2", "new-1"]

    def test_fair_ingestion_processes_orders_before_large_feature_backlog(self, tmp_path):
        """Round-robin quotas should avoid order starvation under heavy feature backlog."""

        features_dir = tmp_path / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        orders_file = tmp_path / "order_log_v1.jsonl"
        core_log = tmp_path / "aurora_core.log"

        heavy_feature_lines = [
            (
                f"2026-01-09 12:00:{i % 60:02d},{i % 1000:03d} - "
                "feature_engineering.FeatureEngineering - INFO - "
                'Calculated features for BTCUSDT: {"obi": "0.1", "rsi": "50.0", "vol": "0.03", "price": "90000"}\n'
            )
            for i in range(10000)
        ]
        (features_dir / "BTCUSDT.log").write_text("".join(heavy_feature_lines), encoding="utf-8")

        order_lines = []
        for i in range(100):
            order_lines.append(
                json.dumps(
                    {
                        "event_type": "ORDER_PLACED",
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "quantity": 0.001,
                        "timestamp": 1_700_000_000 + i,
                        "metadata": {"order_type": "MARKET_ENTRY"},
                    }
                )
            )
        orders_file.write_text("\n".join(order_lines) + "\n", encoding="utf-8")
        core_log.write_text("", encoding="utf-8")

        config = MultiSourceConfig(
            enabled=True,
            features_dir=features_dir,
            orders_file=orders_file,
            core_log=core_log,
            symbols=["BTCUSDT"],
            batch_size=100,
            poll_interval=0.01,
            max_feature_lines_total_per_cycle=1000,
            max_feature_lines_per_symbol_per_cycle=200,
            max_order_lines_per_cycle=100,
            max_core_lines_per_cycle=50,
        )

        first_order_seen_at_feature_count = {"value": None}

        async def feature_handler(_event):
            return None

        tailer = MultiTailer(
            config=config,
            feature_handler=feature_handler,
            state_path=tmp_path / "state.json",
        )

        original_order_handler = tailer._handle_order_event

        async def wrapped_order_handler(entry):
            if first_order_seen_at_feature_count["value"] is None:
                first_order_seen_at_feature_count["value"] = tailer.stats["features_processed"]
            await original_order_handler(entry)

        tailer._handle_order_event = wrapped_order_handler

        async def run_test():
            task = asyncio.create_task(tailer.run())
            await asyncio.sleep(0.4)
            tailer.stop()
            await task

        run_async(run_test(), timeout=5.0)

        assert tailer.stats["orders_processed"] > 0
        assert first_order_seen_at_feature_count["value"] is not None
        assert first_order_seen_at_feature_count["value"] < 5000

    def test_tailer_core_log_invalid_bytes_do_not_crash(self, temp_logs, caplog):
        """Core log with non-UTF8 bytes should be decoded with replacement, not crash loop."""

        # Inject a line with invalid UTF-8 byte sequence.
        bad_line = b"2026-01-09 12:00:02,500 - core - INFO - bad\x8dbyte\n"
        valid_line = (
            b"2026-01-09 12:00:03,000 - aurora_handler.aurora - INFO - "
            b"[BTCUSDT] Position closed (neutral). Starting re-entry cooldown.\n"
        )
        temp_logs["core_log"].write_bytes(bad_line + valid_line)

        config = MultiSourceConfig(
            enabled=True,
            features_dir=temp_logs["features_dir"],
            orders_file=temp_logs["orders_file"],
            core_log=temp_logs["core_log"],
            symbols=["BTCUSDT"],
        )

        tailer = MultiTailer(
            config=config,
            feature_handler=AsyncMock(),
            state_path=temp_logs["root"] / "state.json",
        )

        async def run_test():
            task = asyncio.create_task(tailer.run())
            await asyncio.sleep(0.3)
            tailer.stop()
            await task

        run_async(run_test())

        combined_log = "\n".join([rec.message for rec in caplog.records])
        assert "charmap' codec can't decode" not in combined_log
    
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
        assert episode.event_ts_ms == 1736380000000
        assert episode.features["obi"] == 0.5
        assert episode.side == "BUY"
        assert episode.reward == 0.0  # Default
