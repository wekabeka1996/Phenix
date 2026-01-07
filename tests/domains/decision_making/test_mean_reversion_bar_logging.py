
import os
import time
import shutil
import unittest
import decimal
from unittest.mock import MagicMock, patch

# Domains
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MeanReversion1mStrategy, MRStrategyConfig, MRSignal, MRSignalType
)
from apps.reference.domains.feature_engineering.bar_resampler import Bar
from apps.reference.domains.decision_making.mean_reversion_logger import MeanReversionBarLogger
from apps.reference.config_models import (
    AuroraConfig, 
    StrategiesRegistryConfig,
    StrategiesConfig,
    MeanReversion1mStrategyConfig,
    MRStrategyParamsConfig,
    MRAssetConfig,
    MRRegimeThresholdsConfig
)

class TestMeanReversionBarLogging(unittest.TestCase):
    
    def setUp(self):
        # Create temp logs directory
        self.test_log_dir = "logs/test_mr_logs"
        if os.path.exists(self.test_log_dir):
            shutil.rmtree(self.test_log_dir)
        os.makedirs(self.test_log_dir)
        
        # Mock FSM and Config
        self.fsm = MagicMock()
        self.config = self._create_mock_config()
        
        # Patch init to avoid heavy setup but allow strategy init
        self.handler = MeanReversionHandler(self.fsm, self.config)
        
        # Patch logger to use test dir
        self.handler.bar_logger.log_dir = self.test_log_dir
        self.handler.bar_logger.tsv_path = os.path.join(self.test_log_dir, f"bars_{self.config.strategies.mean_reversion.timeframe_sec}s.tsv")
        self.handler.bar_logger.jsonl_path = os.path.join(self.test_log_dir, f"bars_{self.config.strategies.mean_reversion.timeframe_sec}s.jsonl")
        self.handler.bar_logger._init_tsv_header()

    def tearDown(self):
        if os.path.exists(self.test_log_dir):
            shutil.rmtree(self.test_log_dir)

    def _create_mock_config(self):
        # Create a mock config object instead of real AuroraConfig to avoid populating all 50+ required fields
        config = MagicMock(spec=AuroraConfig)
        
        # Strategies Registry
        strategies_registry = StrategiesRegistryConfig(
            version="1.0",
            arbitration={
                "mode": "priority",
                "window_ms": 100,
                "priority": {"default": 1},
                "logging": {"rejected_why_prefix": "ARB_REJECT", "log_level": "INFO"}
            },
            assignments={"BTCUSDT": ["mean_reversion"]}
        )
        config.strategies_registry = strategies_registry
        
        # Strategies
        mr_config = MeanReversion1mStrategyConfig(
            enabled=True,
            timeframe_sec=60, # 1m for test speed
            strategy=MRStrategyParamsConfig(
                bb_window=20,
                bb_num_std=2.0,
                atr_window=14,
                rsi_window=14,
                entry_threshold=0.05,
                rsi_oversold=30.0,
                rsi_overbought=70.0,
                min_bars=25,
                min_bb_width=0.001,
                max_bb_width=0.05,
                sl_atr_mult=1.5,
                tp_to_mid=True,
                cooldown_sec=60
            ),
            assets={
                "BTCUSDT": MRAssetConfig(
                    enabled=True,
                    allowed_regimes=["FLAT_NORMAL"],
                    position_mode="STRICT"
                )
            },
            regime_thresholds=MRRegimeThresholdsConfig(
                high_vol_pct="0.01",
                low_vol_pct="0.001"
            ),
            regime_sizing={},
            allowed_regimes=["FLAT_NORMAL"],
            risk={
                "position_size_usd": 100.0,
                "max_concurrent_positions": 1,
                "daily_loss_limit_usd": 1000.0,
                "expected_pnl_multiplier": 1.0,
                "fees_pct": 0.001,
                "slippage_pct": 0.001
            },
            emit_trade_intent_directly=False
        )
        
        strategies = MagicMock()
        strategies.mean_reversion = mr_config
        config.strategies = strategies
        
        return config

    def test_log_bar_creation(self):
        """Test that a bar is logged when on_tick completes a bar."""
        symbol = "BTCUSDT"
        
        # Send ticks to complete a bar
        # Ticks: 0s, 30s, 60s (closes bar 0-60)
        base_ts = 1000000000000 # arbitrary start
        
        # 1. Start Bar
        self.handler.on_tick(symbol, decimal.Decimal("50000"), decimal.Decimal("1"), base_ts + 0, "FLAT_NORMAL")
        
        # Check no log yet
        self.assertFalse(os.path.exists(self.handler.bar_logger.tsv_path), "Log should only have header")
        with open(self.handler.bar_logger.tsv_path, 'r') as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 1, "Only header should exist")

        # 2. Add intermediate tick
        self.handler.on_tick(symbol, decimal.Decimal("50050"), decimal.Decimal("1"), base_ts + 30000, "FLAT_NORMAL")

        # 3. Close Bar (Tick at 60s starts new bar, closes old)
        self.handler.on_tick(symbol, decimal.Decimal("50100"), decimal.Decimal("1"), base_ts + 60000, "FLAT_NORMAL")
        
        # Check log Created
        self.assertTrue(os.path.exists(self.handler.bar_logger.tsv_path))
        with open(self.handler.bar_logger.tsv_path, 'r') as f:
            lines = f.readlines()
        
        # Should contain header + 1 bar
        self.assertEqual(len(lines), 2, f"Expected 2 lines (Header + Bar), got {len(lines)}")
        
        # Verify content of last line
        bar_line = lines[-1]
        self.assertIn("BTCUSDT", bar_line)
        self.assertIn("50000", bar_line) # Open
        self.assertIn("50050", bar_line) # High/Close of previous actions? No, Close was 50050 (last tick in bar)
        # Wait: tick 1 @ 50000 (0s)
        # tick 2 @ 50050 (30s) -> High 50050, Low 50000, Close 50050
        # tick 3 @ 50100 (60s) -> Closes 0-60 bar.
        
        # Note: on_tick logic: tick 3 is processed by strategy. add_tick sees new period, returns closed bar.
        # Closed bar includes tick 1 and 2. Tick 3 starts NEXT bar.
        
        self.assertIn("50050.0000", bar_line) # Close
        self.assertIn("neutral:insufficient_bars", bar_line) # Reason (min_bars=25 default)
        
        # Verify JSONL
        self.assertTrue(os.path.exists(self.handler.bar_logger.jsonl_path))
        with open(self.handler.bar_logger.jsonl_path, 'r') as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 1)
            import json
            data = json.loads(lines[0])
            self.assertEqual(data["symbol"], "BTCUSDT")
            self.assertEqual(data["ohlcv"]["c"], "50050")
            self.assertEqual(data["signal"]["type"], "NEUTRAL")

    def test_log_signal_generation(self):
        """Test logging when a real signal is generated (requires enough bars)."""
        symbol = "BTCUSDT"
        
        # Hack strategy to have enough bars and force a signal condition
        strategy = self.handler._strategies[symbol]
        strategy.config.min_bars = 2
        
        base_ts = 1000000000000
        
        # Bar 1: Neutral
        self.handler.on_tick(symbol, decimal.Decimal("100"), decimal.Decimal("1"), base_ts, "FLAT_NORMAL")
        self.handler.on_tick(symbol, decimal.Decimal("100"), decimal.Decimal("1"), base_ts + 60000, "FLAT_NORMAL") # Close Bar 1
        
        # Bar 2: Force Low (Trigger Buy)
        # Need BB to form. With 2 bars, BB is thin? 
        # Actually need bb_window bars for BB. Mock it?
        # Let's mock the strategy's _evaluate_signal to return a LONG signal
        
        with patch.object(MeanReversion1mStrategy, '_evaluate_signal') as mock_eval:
             # Make return a valid signal
             mock_eval.return_value = MRSignal(
                 signal_type=MRSignalType.LONG,
                 symbol=symbol,
                 price=decimal.Decimal("90"),
                 bb=None, # Log should handle None bb
                 flat_regime=None,
                 timestamp_ms=base_ts + 120000,
                 why="test_signal",
                 confidence=decimal.Decimal("0.9"),
                 entry_price=decimal.Decimal("90"),
                 bar=Bar(symbol, 60, decimal.Decimal(100), decimal.Decimal(100), decimal.Decimal(90), decimal.Decimal(90), decimal.Decimal(1), 1, 0, 0)
             )
             
             # Trigger Bar Close
             self.handler.on_tick(symbol, decimal.Decimal("90"), decimal.Decimal("1"), base_ts + 120000, "FLAT_NORMAL")
             
             # Check Log
             with open(self.handler.bar_logger.tsv_path, 'r') as f:
                 lines = f.readlines()
             
             # Header + Bar 1 + Bar 2
             self.assertEqual(len(lines), 3)
             self.assertIn("LONG", lines[-1])
             self.assertIn("test_signal", lines[-1])

if __name__ == '__main__':
    unittest.main()
