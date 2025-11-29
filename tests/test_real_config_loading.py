import pytest
from apps.reference.config_loader import ConfigLoader

def test_real_config_loading():
    loader = ConfigLoader()
    config = loader.load_config()
    
    # Verify Market Data Config (from trading.yaml)
    assert config.trading.market_data is not None
    assert config.trading.market_data.poll_interval_sec == 2.0
    assert config.trading.market_data.api_call_limits.get_recent_trades == 50
    
    # Verify Watchdog Config (from trading.yaml)
    assert config.trading.execution.watchdog["rps_limit"] == 10
    
    # Verify Regime Models Config (from regime.yaml)
    assert config.models is not None
    assert "sma_trend" in config.models
    assert config.models["sma_trend"]["confidence_multiplier"] == 20.0
    assert "volatility" in config.models
    assert config.models["volatility"]["threshold_multiplier"] == 2.0

if __name__ == "__main__":
    pytest.main([__file__])
