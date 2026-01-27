
import os
import shutil
import unittest
from unittest.mock import MagicMock

# Domains
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
from apps.reference.domains.decision_making.mean_reversion_logger import MeanReversionBarLogger
from apps.reference.config_models import (
    AuroraConfig, 
    StrategiesRegistryConfig,
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
            }
        )
        
        strategies = MagicMock()
        strategies.mean_reversion = mr_config
        config.strategies = strategies
        
        return config

    # NOTE: test_log_bar_creation and test_log_signal_generation were removed
    # They used handler.on_tick() which was deprecated dead code (T2B-06).
    # MR now uses CMD:PROCESS_STRATEGY exclusively (T2B-03).
    # New tests should use _on_process_strategy() or CMD:PROCESS_STRATEGY events.


if __name__ == '__main__':
    unittest.main()
