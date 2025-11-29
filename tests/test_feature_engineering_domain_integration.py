import pytest
from unittest.mock import MagicMock
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

class TestFeatureEngineeringIntegration:
    def test_feature_engineering_uses_domains_config(self, mock_fsm, root_mock_config):
        """Verify FeatureEngineering initializes with values from domains config."""
        # Initialize component
        fe = FeatureEngineering(mock_fsm, root_mock_config)
        
        # Initialize state for a symbol to trigger config loading
        symbol = "BTCUSDT"
        fe._init_symbol_state(symbol)
        state = fe.symbol_state[symbol]
        
        # Verify values match domains.yaml (loaded into state or used in logic)
        # ema_short = 3 -> alpha = 2/(3+1) = 0.5
        # ema_long = 7 -> alpha = 2/(7+1) = 0.25
        assert state["ema3_alpha"] == 0.5
        assert state["ema7_alpha"] == 0.25
        
        # volume_sma_length = 5 -> vol_hist maxlen
        assert state["vol_hist"].maxlen == 5
        
        # volatility_sma_length = 10 -> range_hist maxlen
        assert state["range_hist"].maxlen == 10
