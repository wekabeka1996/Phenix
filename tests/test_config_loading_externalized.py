import pytest
from decimal import Decimal
from apps.reference.config_models import AuroraConfig, MarketDataConfig, WatchdogConfig, RegimeDetectorConfig
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from unittest.mock import MagicMock

class TestExternalizedConfigs:
    def test_market_data_config_loading(self):
        config_dict = {
            "market_data": {
                "poll_interval_sec": 5.0,
                "websocket_streams": ["trade"],
                "api_call_limits": {
                    "get_recent_trades": 100,
                    "get_klines": {"interval": "5m", "limit": 10}
                }
            },
            "binance_api": {
                "testnet": {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "rest_url": "https://test.url"
                }
            },
            "trading_mode": "testnet"
        }
        # Mock FSM
        fsm = MagicMock()
        
        # Initialize connector with config dict
        connector = MarketDataConnector(fsm, config_dict)
        
        # Verify config values are used (we need to check internal state or mocked calls)
        # Since we can't easily check internal local variables of methods without running them,
        # we can check if the config object attached to self has the right values.
        # However, MarketDataConnector converts dict to object internally if needed or uses it directly.
        
        # Let's verify the config object structure if possible, or just that it doesn't crash.
        assert connector.config["market_data"]["poll_interval_sec"] == 5.0
        assert connector.config["market_data"]["api_call_limits"]["get_recent_trades"] == 100

    def test_watchdog_config_loading(self):
        config_dict = {
            "ack_ttl_ms": 5000,
            "fill_ttl_ms": 10000,
            "check_interval_ms": 500,
            "rps_limit": 20
        }
        
        watchdog = OrderTimeoutWatchdog(config=config_dict)
        
        assert watchdog.ack_ttl_ms == 5000
        assert watchdog.fill_ttl_ms == 10000
        assert watchdog.check_interval_ms == 500
        assert watchdog._rps_limit == 20

    def test_regime_detector_config_loading(self):
        config_dict = {
            "models": {
                "sma_trend": {
                    "confidence_multiplier": 30.0,
                    "confidence_min": 0.6,
                    "confidence_max": 0.9
                },
                "volatility": {
                    "high_vol_confidence_multiplier": 4.0,
                    "low_vol_confidence_multiplier": 5.0
                },
                "mean_reversion": {
                    "confidence_multiplier": 200.0
                }
            }
        }
        fsm = MagicMock()
        detector = RegimeDetector(config_dict, fsm)
        
        # Verify internal config state
        # We can check if the logic uses these values by calling _calculate_confidence or similar if accessible
        # Or just check that initialization didn't fail and config is stored
        
        assert detector.config["models"]["sma_trend"]["confidence_multiplier"] == 30.0
        
        # Test _calculate_confidence logic indirectly if possible or via private method access
        # _calculate_confidence is private, but we can access it for testing
        conf = detector._calculate_confidence(Decimal("4050"), Decimal("3900"))
        # spread = (4050-3900)/3900 = 0.03846
        # conf = 0.03846 * 30.0 = 1.15 -> capped at 0.9 (max)
        assert conf == Decimal("0.9")

if __name__ == "__main__":
    pytest.main([__file__])
