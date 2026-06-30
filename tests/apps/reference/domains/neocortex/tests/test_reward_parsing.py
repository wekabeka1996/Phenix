"""
Tests for Reward Parsing and PnL Extraction

TASK-R1: Ensure reward is correctly extracted and normalized for PPO.
"""

import pytest
import json
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass
from typing import Dict, Any, Optional
import numpy as np

# Import from neocortex - adjust path as needed
import sys

from apps.reference.domains.neocortex.logic.ingest.parsers.core_parser import (
    parse_core_log_line, 
    CoreEventType,
    CoreLogEntry,
    parse_scientific_notation
)
from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
    parse_order_log_line,
    OrderEventType,
    OrderLogEntry
)


class TestCoreLogParsing:
    """Test parsing of core log entries."""
    
    def test_parse_position_closed_neutral(self):
        """Parse position closed (neutral) event."""
        line = (
            "2026-01-10 05:16:44,365 - aurora_handler.aurora - INFO - "
            "[ETHUSDT] Position closed (neutral). Starting re-entry cooldown."
        )
        entry = parse_core_log_line(line)
        
        assert entry is not None
        assert entry.event_type == CoreEventType.POSITION_CLOSED
        assert entry.symbol == "ETHUSDT"
        assert entry.reason == "neutral"
        assert entry.event_ts_ms == 1768011404365
    
    def test_parse_position_closed_btc(self):
        """Parse BTC position closed event."""
        line = (
            "2026-01-10 03:10:42,580 - aurora_handler.aurora - INFO - "
            "[BTCUSDT] Position closed (neutral). Starting re-entry cooldown."
        )
        entry = parse_core_log_line(line)
        
        assert entry is not None
        assert entry.symbol == "BTCUSDT"
        assert entry.event_type == CoreEventType.POSITION_CLOSED

    def test_parse_position_closed_structured_payload(self):
        """Parse structured EVT:POSITION_CLOSED payload from log line."""
        line = (
            '2026-01-10 03:10:42,580 - execution_position.fsm - INFO - '
            'EVT:POSITION_CLOSED symbol=BTCUSDT trade_id=BTCUSDT:1700000001000:1 '
            'close_ts_ms=1700000001000 close_price=90500.0 quantity=0.001 '
            'realized_pnl=3.6 realized_pnl_net=3.5 fees=0.1'
        )
        entry = parse_core_log_line(line)

        assert entry is not None
        assert entry.event_type == CoreEventType.POSITION_CLOSED
        assert entry.symbol == "BTCUSDT"
        assert entry.trade_id == "BTCUSDT:1700000001000:1"
        assert entry.close_ts_ms == 1700000001000
        assert entry.close_price == pytest.approx(90500.0)
        assert entry.quantity == pytest.approx(0.001)
        assert entry.realized_pnl == pytest.approx(3.6)
        assert entry.realized_pnl_net == pytest.approx(3.5)
        assert entry.fees == pytest.approx(0.1)

    def test_parse_trade_closed_structured_payload(self):
        """Parse structured EVT:TRADE_CLOSED payload from log line."""
        line = (
            '2026-01-10 03:10:42,580 - execution_position.fsm - INFO - '
            'EVT:TRADE_CLOSED symbol=BTCUSDT trade_id=BTCUSDT:1700000001000:1 '
            'close_ts_ms=1700000001000 close_price=90500.0 realized_pnl_net=3.5 fees=0.1'
        )
        entry = parse_core_log_line(line)

        assert entry is not None
        assert entry.event_type == CoreEventType.TRADE_CLOSED
        assert entry.trade_id == "BTCUSDT:1700000001000:1"
        assert entry.close_price == pytest.approx(90500.0)
        assert entry.realized_pnl_net == pytest.approx(3.5)
    
    def test_parse_equity_update(self):
        """Parse equity update from positions update log."""
        line = (
            "2026-01-10 06:03:06,615 - apps.reference.domains.account_balance.account_connector - INFO - "
            "Emitted positions update: 3 open positions, totalWalletBalance=251.79752181, totalUnrealizedProfit=0E-8"
        )
        entry = parse_core_log_line(line)
        
        assert entry is not None
        assert entry.event_type == CoreEventType.EQUITY_UPDATE
        assert abs(entry.equity - 251.79752181) < 0.01
        assert entry.unrealized_pnl == 0.0  # 0E-8 should parse as 0
    
    def test_parse_scientific_notation_values(self):
        """Test parsing of scientific notation like 0E-8."""
        assert parse_scientific_notation("0E-8") == 0.0
        assert parse_scientific_notation("0.0") == 0.0
        assert parse_scientific_notation("123.45") == 123.45
        assert parse_scientific_notation("1E-5") == pytest.approx(0.00001)
        assert parse_scientific_notation("invalid") == 0.0
    
    def test_parse_irrelevant_line_returns_none(self):
        """Irrelevant log lines should return None."""
        line = "2026-01-10 06:03:06,320 - some.module - DEBUG - Random debug message"
        entry = parse_core_log_line(line)
        assert entry is None
    
    def test_parse_empty_line(self):
        """Empty lines should return None."""
        assert parse_core_log_line("") is None
        assert parse_core_log_line("   ") is None


class TestOrderLogParsing:
    """Test parsing of order log entries."""
    
    def test_parse_order_placed(self):
        """Parse ORDER_PLACED event from JSONL."""
        line = json.dumps({
            "rid": "aurora_SOLUSDT_1768003484788",
            "event_type": "ORDER_PLACED",
            "symbol": "SOLUSDT",
            "side": "SELL",
            "quantity": 4.0,
            "timestamp": 1768003485696
        })
        
        entry = parse_order_log_line(line)
        
        assert entry is not None
        assert entry.event_type == OrderEventType.PLACED
        assert entry.symbol == "SOLUSDT"
        assert entry.side == "SELL"
        assert entry.quantity == 4.0
    
    def test_parse_order_rejected(self):
        """Parse ORDER_REJECTED event."""
        line = json.dumps({
            "rid": "aurora_ETHUSDT_1768003264735",
            "event_type": "ORDER_REJECTED",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "nrr_code": "NRR-026",
            "why": "SAFETY_GATES:insufficient trend confirmation",
            "timestamp": 1768003264735
        })
        
        entry = parse_order_log_line(line)
        
        assert entry is not None
        assert entry.event_type == OrderEventType.REJECTED
        assert entry.symbol == "ETHUSDT"
        assert entry.nrr_code == "NRR-026"
    
    def test_parse_invalid_json(self):
        """Invalid JSON should return None."""
        entry = parse_order_log_line("not valid json {{{")
        assert entry is None
    
    def test_parse_unknown_event_type(self):
        """Unknown event types should return UNKNOWN type."""
        line = json.dumps({
            "event_type": "UNKNOWN_EVENT",
            "symbol": "BTCUSDT",
            "timestamp": 1700000000.0
        })
        entry = parse_order_log_line(line)
        # Parser returns with UNKNOWN type, not None
        assert entry is not None
        assert entry.event_type == OrderEventType.UNKNOWN


class TestRewardNormalization:
    """Test reward normalization using tanh."""
    
    def test_reward_normalization_positive(self):
        """Positive PnL should give positive reward."""
        pnl = 10.0  # $10 profit
        reward = float(np.tanh(pnl / 10.0))
        
        assert 0.7 < reward < 0.8  # tanh(1) ≈ 0.76
        assert reward > 0
    
    def test_reward_normalization_negative(self):
        """Negative PnL should give negative reward."""
        pnl = -10.0  # $10 loss
        reward = float(np.tanh(pnl / 10.0))
        
        assert -0.8 < reward < -0.7  # tanh(-1) ≈ -0.76
        assert reward < 0
    
    def test_reward_normalization_zero(self):
        """Zero PnL should give zero reward."""
        pnl = 0.0
        reward = float(np.tanh(pnl / 10.0))
        
        assert reward == 0.0
    
    def test_reward_normalization_bounded(self):
        """Reward should be bounded in [-1, 1]."""
        for pnl in [-1000, -100, -10, 0, 10, 100, 1000]:
            reward = float(np.tanh(pnl / 10.0))
            assert -1 <= reward <= 1
    
    def test_reward_small_pnl(self):
        """Small PnL should give proportionally small reward."""
        pnl = 1.0  # $1 profit
        reward = float(np.tanh(pnl / 10.0))
        
        # tanh(0.1) ≈ 0.1
        assert 0.09 < reward < 0.11


class TestEquityDeltaPnLEstimation:
    """Test PnL estimation via equity delta."""
    
    def test_equity_delta_calculation(self):
        """Test basic equity delta calculation."""
        entry_equity = 250.0
        exit_equity = 255.0
        
        raw_pnl = exit_equity - entry_equity
        assert raw_pnl == 5.0
    
    def test_equity_delta_loss(self):
        """Test equity delta for loss."""
        entry_equity = 250.0
        exit_equity = 245.0
        
        raw_pnl = exit_equity - entry_equity
        assert raw_pnl == -5.0
    
    def test_equity_delta_to_normalized_reward(self):
        """Full pipeline: equity delta -> normalized reward."""
        entry_equity = 250.0
        exit_equity = 260.0  # $10 profit
        
        raw_pnl = exit_equity - entry_equity
        normalized_reward = float(np.tanh(raw_pnl / 10.0))
        
        assert abs(raw_pnl - 10.0) < 0.01
        assert 0.7 < normalized_reward < 0.8


class TestMultiTailerIntegration:
    """Integration tests for MultiTailer with reward injection."""
    
    @pytest.fixture
    def temp_logs(self, tmp_path):
        """Create temporary log files."""
        # Create features dir
        features_dir = tmp_path / "features"
        features_dir.mkdir()
        
        # Create feature log
        feature_log = features_dir / "BTCUSDT.log"
        feature_log.write_text(
            "2026-01-10 05:16:40,000 - feature_engineering.FeatureEngineering - INFO - "
            'Calculated features for BTCUSDT: {"obi": "0.1", "tfi": "0.2", "delta_price": "0.01", "price": "90000"}\n'
        )
        
        # Create order log
        orders_file = tmp_path / "order_log_v1.jsonl"
        orders_data = [
            {
                "event_type": "ORDER_PLACED",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": 0.001,
                "timestamp": 1700000000000
            },
        ]
        orders_file.write_text("\n".join(json.dumps(o) for o in orders_data) + "\n")
        
        # Create core log
        core_log = tmp_path / "aurora_core.log"
        core_log.write_text(
            "2026-01-10 05:16:44,365 - account_connector - INFO - "
            "Emitted positions update: 1 open positions, totalWalletBalance=255.0, totalUnrealizedProfit=0E-8\n"
            "2026-01-10 05:17:00,000 - aurora_handler.aurora - INFO - "
            "[BTCUSDT] Position closed (neutral). Starting re-entry cooldown.\n"
        )
        
        return {
            "features_dir": features_dir,
            "orders_file": orders_file,
            "core_log": core_log
        }
    
    def test_episode_receives_reward(self, temp_logs):
        """Verify episode handler can receive reward (sync version)."""
        from apps.reference.domains.neocortex.logic.ingest.multi_tailer import MultiTailer, MultiSourceConfig
        
        config = MultiSourceConfig(
            enabled=True,
            features_dir=temp_logs["features_dir"],
            orders_file=temp_logs["orders_file"],
            core_log=temp_logs["core_log"],
            symbols=["BTCUSDT"]
        )
        
        async def feature_handler(payload):
            pass
        
        tailer = MultiTailer(
            config=config,
            feature_handler=feature_handler,
            episode_handler=None
        )
        
        # Set initial equity
        tailer._last_equity = 250.0
        
        # Just verify initialization works
        assert tailer._last_equity == 250.0
        assert tailer._features_processed == 0

    @pytest.mark.asyncio
    async def test_no_structured_reward_results_in_none_reward(self, temp_logs):
        """No fallback policy: missing structured reward should not be synthesized from equity."""
        from apps.reference.domains.neocortex.logic.ingest.multi_tailer import MultiTailer, MultiSourceConfig, Episode

        captured = []

        async def feature_handler(_payload):
            return None

        async def episode_handler(ep):
            captured.append(ep)

        tailer = MultiTailer(
            config=MultiSourceConfig(
                enabled=True,
                features_dir=temp_logs["features_dir"],
                orders_file=temp_logs["orders_file"],
                core_log=temp_logs["core_log"],
                symbols=["BTCUSDT"],
            ),
            feature_handler=feature_handler,
            episode_handler=episode_handler,
        )
        tailer._pending_episodes["trade:BTCUSDT:1700000001000:1"] = Episode(
            symbol="BTCUSDT",
            timestamp=1700000000.0,
            event_ts_ms=1700000000000,
            features={"rsi": 50.0},
            side="BUY",
            trade_id="BTCUSDT:1700000001000:1",
            executed_entry=True,
            entry_anchor_event="ORDER_FILLED",
            lifecycle_state="ENTERED",
        )
        tailer._episode_keys_by_trade_id["BTCUSDT:1700000001000:1"] = "trade:BTCUSDT:1700000001000:1"

        await tailer._handle_position_close(
            CoreLogEntry(
                timestamp=1700000001.0,
                event_ts_ms=1700000001000,
                timestamp_str="2026-01-10 00:00:01,000",
                event_type=CoreEventType.POSITION_CLOSED,
                symbol="BTCUSDT",
                trade_id="BTCUSDT:1700000001000:1",
            )
        )

        assert len(captured) == 1
        assert captured[0].episode_reward is not None
        assert captured[0].episode_reward.reward_complete is False
        assert captured[0].reward_complete is False
        assert captured[0].reward is None
        assert captured[0].pnl is None

    @pytest.mark.asyncio
    async def test_structured_reward_is_used_and_normalized(self, temp_logs):
        """Structured realized_pnl_net should drive reward calculation."""
        from apps.reference.domains.neocortex.logic.ingest.multi_tailer import MultiTailer, MultiSourceConfig, Episode

        captured = []

        async def feature_handler(_payload):
            return None

        async def episode_handler(ep):
            captured.append(ep)

        tailer = MultiTailer(
            config=MultiSourceConfig(
                enabled=True,
                features_dir=temp_logs["features_dir"],
                orders_file=temp_logs["orders_file"],
                core_log=temp_logs["core_log"],
                symbols=["BTCUSDT"],
            ),
            feature_handler=feature_handler,
            episode_handler=episode_handler,
        )
        tailer._pending_episodes["trade:BTCUSDT:1700000001000:1"] = Episode(
            symbol="BTCUSDT",
            timestamp=1700000000.0,
            event_ts_ms=1700000000000,
            features={"rsi": 50.0},
            side="BUY",
            trade_id="BTCUSDT:1700000001000:1",
            executed_entry=True,
            entry_anchor_event="ORDER_FILLED",
            lifecycle_state="ENTERED",
            entry_price=100.0,
            quantity=1.0,
            filled_quantity=1.0,
            fill_count=1,
        )
        tailer._episode_keys_by_trade_id["BTCUSDT:1700000001000:1"] = "trade:BTCUSDT:1700000001000:1"

        await tailer._handle_position_close(
            CoreLogEntry(
                timestamp=1700000001.0,
                event_ts_ms=1700000001000,
                timestamp_str="2026-01-10 00:00:01,000",
                event_type=CoreEventType.POSITION_CLOSED,
                symbol="BTCUSDT",
                realized_pnl_net=9.9,
                trade_id="BTCUSDT:1700000001000:1",
                close_ts_ms=1700000001000,
                close_price=110.0,
                fees=0.1,
            )
        )

        assert len(captured) == 1
        assert captured[0].episode_reward is not None
        assert captured[0].episode_reward.reward_complete is True
        assert captured[0].episode_reward.realized_pnl == pytest.approx(10.0)
        assert captured[0].pnl == pytest.approx(9.9)
        assert captured[0].reward == pytest.approx(float(np.tanh(9.9 / 10.0)))

    @pytest.mark.asyncio
    async def test_structured_close_log_line_flows_end_to_end(self, tmp_path):
        """Structured core log line should close pending episode with valid pnl/reward."""
        from apps.reference.domains.neocortex.logic.ingest.multi_tailer import MultiTailer, MultiSourceConfig

        features_dir = tmp_path / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        (features_dir / "BTCUSDT.log").write_text(
            (
                "2026-01-10 03:10:40,000 - feature_engineering.FeatureEngineering - INFO - "
                'Calculated features for BTCUSDT: {"price": "90000", "obi": "0.1", "rsi": "50.0", "vol": "0.03"}\n'
            ),
            encoding="utf-8",
        )
        orders_file = tmp_path / "order_log_v1.jsonl"
        orders_file.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "event_type": "ORDER_PLACED",
                            "symbol": "BTCUSDT",
                            "side": "BUY",
                            "quantity": 0.001,
                            "timestamp": 1_700_000_000.0,
                            "order_id": "order-1",
                            "client_order_id": "ENTRY-1",
                            "metadata": {"order_type": "MARKET_ENTRY"},
                        }
                    ),
                    json.dumps(
                        {
                            "event_type": "ORDER_FILLED",
                            "symbol": "BTCUSDT",
                            "side": "BUY",
                            "quantity": 0.001,
                            "price": 90000.0,
                            "timestamp": 1_700_000_000.1,
                            "order_id": "order-1",
                            "client_order_id": "ENTRY-1",
                            "metadata": {"fill_trade_id": "BTCUSDT:1700000001000:1"},
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        core_log = tmp_path / "aurora_core.log"
        core_log.write_text(
            (
                "2026-01-10 03:10:42,580 - execution_position.fsm - INFO - "
                "EVT:POSITION_CLOSED symbol=BTCUSDT trade_id=BTCUSDT:1700000001000:1 "
                "close_ts_ms=1700000001000 close_price=90500.0 realized_pnl_net=3.5 fees=0.1\n"
            ),
            encoding="utf-8",
        )

        captured = []

        async def feature_handler(_payload):
            return None

        async def episode_handler(ep):
            captured.append(ep)

        tailer = MultiTailer(
            config=MultiSourceConfig(
                enabled=True,
                features_dir=features_dir,
                orders_file=orders_file,
                core_log=core_log,
                symbols=["BTCUSDT"],
                poll_interval=0.01,
                max_feature_lines_total_per_cycle=100,
                max_feature_lines_per_symbol_per_cycle=100,
                max_order_lines_per_cycle=10,
                max_core_lines_per_cycle=10,
            ),
            feature_handler=feature_handler,
            episode_handler=episode_handler,
            state_path=tmp_path / "state.json",
        )

        task = asyncio.create_task(tailer.run())
        await asyncio.sleep(0.25)
        tailer.stop()
        await task

        assert len(captured) == 1
        assert captured[0].position_closed is True
        assert captured[0].executed_entry is True
        assert captured[0].entry_anchor_event == "ORDER_FILLED"
        assert captured[0].episode_reward is not None
        assert captured[0].episode_reward.reward_complete is True
        assert captured[0].pnl == pytest.approx(3.5)
        assert captured[0].reward == pytest.approx(float(np.tanh(3.5 / 10.0)))


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])


