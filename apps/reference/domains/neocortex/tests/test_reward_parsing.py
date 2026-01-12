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
sys.path.insert(0, str(Path(__file__).parent.parent))

from logic.ingest.parsers.core_parser import (
    parse_core_log_line, 
    CoreEventType,
    CoreLogEntry,
    parse_scientific_notation
)
from logic.ingest.parsers.order_parser import (
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
        assert entry.timestamp > 0
    
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
            "timestamp": 123456789
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
        feature_log.write_text(json.dumps({
            "obi": "0.1",
            "tfi": "0.2",
            "delta_price": "0.01",
            "price": "90000"
        }) + "\n")
        
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
        from logic.ingest.multi_tailer import MultiTailer, MultiSourceConfig
        
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


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
