import pytest
from unittest.mock import MagicMock, patch
from apps.reference.config_symbols import get_trading_symbols, get_first_symbol
from apps.reference.config_loader import ConfigLoader, AuroraConfig
from pydantic import ValidationError

class TestConfigSymbolsHardcodeRemoval:
    
    def test_get_trading_symbols_raises_error_when_no_config(self):
        """Test that get_trading_symbols raises ValueError when no symbols are configured."""
        # Mock get_config to return an empty config or raise exception
        with patch('apps.reference.config_loader.get_config') as mock_get_config:
            # Mock config object structure
            mock_config = MagicMock()
            # Simulate missing instruments
            mock_config.trading.instruments = {}
            mock_get_config.return_value = mock_config
            
            # Also mock vfoundation config to fail
            with patch('vfoundation.config.config', new=MagicMock()) as mock_vfound_config:
                del mock_vfound_config.trading # Simulate missing trading section
                
                with pytest.raises(ValueError, match="No trading symbols configured"):
                    get_trading_symbols()

    def test_get_trading_symbols_returns_configured_symbols(self):
        """Test that get_trading_symbols returns symbols from config."""
        with patch('apps.reference.config_loader.get_config') as mock_get_config:
            mock_config = MagicMock()
            mock_config.trading.instruments = {"BTCUSDT": {}, "ETHUSDT": {}}
            mock_get_config.return_value = mock_config
            
            symbols = get_trading_symbols()
            assert "BTCUSDT" in symbols
            assert "ETHUSDT" in symbols
            assert len(symbols) == 2

    def test_config_loader_validates_symbols_to_track(self):
        """Test that ConfigLoader correctly loads symbols_to_track."""
        # Create a dummy config dict
        config_dict = {
            "trading_mode": "testnet",
            "binance_api": {"testnet": {"api_key": "k", "api_secret": "s"}},
            "trading": {
                "symbols_to_track": ["SOLUSDT", "AVAXUSDT"],
                "instruments": {"SOLUSDT": {"symbol": "SOLUSDT"}}
            }
        }
        
        # Validate using Pydantic model directly
        config = AuroraConfig(**config_dict)
        assert config.trading.symbols_to_track == ["SOLUSDT", "AVAXUSDT"]

    def test_config_loader_defaults_symbols_to_track_to_empty_list(self):
        """Test that symbols_to_track defaults to empty list if missing."""
        config_dict = {
            "trading_mode": "testnet",
            "binance_api": {"testnet": {"api_key": "k", "api_secret": "s"}},
            "trading": {
                "instruments": {"SOLUSDT": {"symbol": "SOLUSDT"}}
            }
        }
        config = AuroraConfig(**config_dict)
        assert config.trading.symbols_to_track == []

