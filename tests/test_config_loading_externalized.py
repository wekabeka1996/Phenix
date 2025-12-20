import pytest
from decimal import Decimal
from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.config_loader import ConfigLoader
from unittest.mock import MagicMock

class TestExternalizedConfigs:
    def test_market_data_config_loading(self):
        try:
            from apps.reference.domains.market_data import market_data_connector as mdc
        except (ModuleNotFoundError, ImportError) as e:
            pytest.skip(f"MarketDataConnector deps not available: {e}")

        if getattr(mdc, "aiohttp", None) is None:
            pytest.skip("aiohttp not available for MarketDataConnector")

        MarketDataConnector = mdc.MarketDataConnector

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

        # Strict object config contract: dict config is forbidden.
        with pytest.raises(TypeError):
            MarketDataConnector(fsm, config_dict)

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
        cfg = ConfigLoader().load_config()
        fsm = MagicMock()
        fsm.emit = MagicMock()
        fsm.listen = MagicMock()
        detector = RegimeDetector(cfg, fsm)

        assert detector.model_config.confidence_multiplier == cfg.models.sma_trend.confidence_multiplier

        conf = detector._calculate_confidence(Decimal("4050"), Decimal("3900"))
        assert conf > Decimal("0.7")
        assert conf <= Decimal(str(cfg.models.sma_trend.confidence_max))

if __name__ == "__main__":
    pytest.main([__file__])
