import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import asyncio
from apps.reference.domains.exchange_filters.validator import FilterMismatchError

# Import main (be careful not to execute module level code if any)
from apps.reference.main import main

class TestStartupFiltersWiring:
    
    @patch("apps.reference.main.ConfigLoader")
    @patch("apps.reference.main.BinanceAdapter")
    @patch("apps.reference.main.validate_instruments_on_startup")
    @patch("apps.reference.main.WALGarbageCollector")
    @patch("apps.reference.main.AlertManager")
    # Entropy monitor might be imported locally, so patch where it is used or patch sys.modules
    @patch("vfoundation.obs.entropy_monitor.EntropyMonitor") 
    def test_startup_validation_blocks_on_mismatch(
        self, 
        mock_entropy, 
        mock_alerts, 
        mock_wal, 
        mock_validate_func, 
        mock_adapter_cls, 
        mock_loader_cls
    ):
        """TASK-EXF-E2E-STARTUP-10: Verify that FilterMismatchError triggers SystemExit(1)."""
        
        # 1. Setup Mock Config
        mock_config = MagicMock()
        mock_config.system.validate_instruments_on_startup = True
        mock_config.trading_mode = "testnet"
        # Mock nested attributes
        mock_config.binance_api.testnet.api_key = "test_key"
        mock_config.binance_api.testnet.api_secret = "test_secret"
        mock_config.instruments = {} # Empty is fine, we just want to reach validation call
        
        mock_loader_instance = mock_loader_cls.return_value
        mock_loader_instance.load_config.return_value = mock_config
        
        # Setup Adapter close for finally block
        mock_adapter_instance = mock_adapter_cls.return_value
        mock_adapter_instance.close = AsyncMock()
        
        # 2. Setup Validator to raise FilterMismatchError
        # asyncio.run() needs a coroutine.
        async def async_raise(*args, **kwargs):
            raise FilterMismatchError([]) # Empty list of mismatches
            
        mock_validate_func.side_effect = async_raise
        
        # 3. Expect SystemExit
        with pytest.raises(SystemExit) as exc:
            main()
            
        assert exc.value.code == 1
        
        # Verify adapter was created
        mock_adapter_cls.assert_called()
        # Verify validation was called
        mock_validate_func.assert_called()
        
    @patch("apps.reference.main.ConfigLoader")
    @patch("apps.reference.main.BinanceAdapter")
    @patch("apps.reference.main.validate_instruments_on_startup")
    @patch("apps.reference.main.WALGarbageCollector")
    @patch("apps.reference.main.AlertManager")
    @patch("vfoundation.obs.entropy_monitor.EntropyMonitor") 
    @patch("apps.reference.main.initialize_domains") # Stop before reaching real domains
    def test_startup_validation_proceeds_on_success(
        self,
        mock_init_domains,
        mock_entropy, 
        mock_alerts, 
        mock_wal, 
        mock_validate_func, 
        mock_adapter_cls, 
        mock_loader_cls
    ):
        """TASK-EXF-E2E-STARTUP-10: Verify that successful validation proceeds to initialization."""
        
        # 1. Setup Mock Config
        mock_config = MagicMock()
        mock_config.system.validate_instruments_on_startup = True
        mock_config.trading_mode = "testnet"
        mock_config.binance_api.testnet.api_key = "test_key"
        mock_config.instruments = {}
        
        mock_loader_instance = mock_loader_cls.return_value
        mock_loader_instance.load_config.return_value = mock_config
        
        # Setup Adapter instance to handle await close()
        mock_adapter_instance = mock_adapter_cls.return_value
        mock_adapter_instance.close = AsyncMock()
        
        # 2. Setup Validator to succeed
        async def async_success(*args, **kwargs):
            return {} # No mismatches
            
        mock_validate_func.side_effect = async_success
        
        # 3. We want to stop main() after validation to avoid running the whole app loop.
        # We can interrupt it by having initialize_domains raise a special exception or simply Mocking it.
        # But main() continues to WalGC and AlertManager AFTER config load, then "Initialize Multi-TF...", then main loop.
        # It's hard to stop main() gracefully without SystemExit.
        # We can mock Thread to do nothing, and mock FSMCore to do nothing.
        # BUT we only want to ensure validation PASSED.
        
        # Let's mock WALGarbageCollector to raise a special "TestSuccess" exception to break flow?
        # No, WALGC is started after validation.
        # So if we reach WALGC, validation passed.
        mock_wal.side_effect = RuntimeError("Validation Passed, Stopping Test")
        
        with pytest.raises(RuntimeError, match="Validation Passed"):
            main()
            
        mock_validate_func.assert_called()
