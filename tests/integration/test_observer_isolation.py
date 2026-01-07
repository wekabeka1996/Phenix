
import pytest
from unittest.mock import MagicMock, patch
from apps.reference.domains.account_observer.account_observer import AccountObserver
from apps.reference.config_loader import AuroraConfig

class TestAccountObserverIsolation:
    """
    [PART B] Wiring Test: Verify AccountObserver isolation in Futures mode.
    
    Goal: Ensure AccountObserver does NOT instantiate a Spot Client (binance.client.Client)
    when configured for Futures (or explicitly disabled via config).
    """
    
    @pytest.fixture
    def mock_aurora_config(self):
        """Mock AuroraConfig."""
        cfg = MagicMock(spec=AuroraConfig)
        cfg.trading_mode = "live"
        cfg.binance_api = MagicMock()
        cfg.binance_api.live.api_key = "dummy_key"
        cfg.binance_api.live.api_secret = "dummy_secret"
        return cfg

    @patch("apps.reference.domains.account_observer.account_observer.DomainConfigResolver")
    @patch("apps.reference.domains.account_observer.account_observer.Client")
    def test_observer_ignores_spot_client_in_futures_mode(self, MockClient, MockResolver, mock_aurora_config):
        """
        Verify that when market_type='futures', the Spot Client is NOT initialized.
        """
        # Setup mock domain config
        mock_domain_cfg = MagicMock()
        mock_domain_cfg.market_type = "futures"
        mock_domain_cfg.poll_interval_sec = 1
        mock_domain_cfg.trade_limit = 10
        mock_domain_cfg.symbols = ["BTCUSDT"]
        
        # Configure Resolver to return this config
        MockResolver.return_value.get_account_observer.return_value = mock_domain_cfg
        
        # 1. Initialize Observer
        # We pass None for fsm as it's not used in __init__ except for assignment
        observer = AccountObserver(None, mock_aurora_config)
        
        # 2. Assert Client was NOT called
        MockClient.assert_not_called()
        
        # 3. Assert internal client is None or strictly disabled
        assert observer.client is None, "Spot Client should be None in futures mode"
        
    @patch("apps.reference.domains.account_observer.account_observer.DomainConfigResolver")
    @patch("apps.reference.domains.account_observer.account_observer.Client") 
    def test_observer_starts_spot_client_in_spot_mode(self, MockClient, MockResolver, mock_aurora_config):
        """
        Control Test: Verify logic still works for Spot mode (backward compat).
        """
        # Setup mock domain config
        mock_domain_cfg = MagicMock()
        mock_domain_cfg.market_type = "spot"
        mock_domain_cfg.poll_interval_sec = 1
        mock_domain_cfg.trade_limit = 10
        mock_domain_cfg.symbols = ["BTCUSDT"]
        
        MockResolver.return_value.get_account_observer.return_value = mock_domain_cfg
        
        observer = AccountObserver(None, mock_aurora_config)
        
        MockClient.assert_called_once()
        assert observer.client is not None
