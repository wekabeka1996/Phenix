"""
Tests for config_symbols single source of truth (no dual import).

CFG-STRATEGIES-SSOT-03-REGISTRY-DRIVEN-LOADING-AND-ONE-CONFIG-TRUTH
"""

import pytest
from unittest.mock import MagicMock, patch


class TestConfigSymbolsOneTruth:
    """Test that config_symbols has ONLY one config access path (no dual import fallback)"""
    
    def test_get_trading_symbols_uses_only_get_config(self):
        """
        Test that get_trading_symbols uses ONLY get_config() (no vfoundation fallback).
        
        CFG-STRATEGIES-SSOT-03: Single source of truth - eliminate dual import.
        """
        from apps.reference.config_symbols import get_trading_symbols
        
        # Mock get_config to return valid config
        mock_config = MagicMock()
        mock_config.instruments = {
            "BTCUSDT": MagicMock(),
            "ETHUSDT": MagicMock()
        }
        
        # Patch at config_loader level (where get_config is defined)
        with patch('apps.reference.config_loader.get_config', return_value=mock_config):
            symbols = get_trading_symbols()
            assert symbols == ["BTCUSDT", "ETHUSDT"]
    
    def test_get_trading_symbols_fails_without_config(self):
        """
        Test that get_trading_symbols raises ValueError if get_config() fails (no fallback).
        
        CFG-STRATEGIES-SSOT-03: Fail-closed - no silent vfoundation fallback.
        """
        from apps.reference.config_symbols import get_trading_symbols
        
        # Mock get_config to raise exception
        with patch('apps.reference.config_loader.get_config', side_effect=Exception("Config unavailable")):
            with pytest.raises(ValueError) as exc_info:
                get_trading_symbols()
            
            # VERIFY: error message indicates config failure (not fallback)
            error_msg = str(exc_info.value)
            assert "CRITICAL" in error_msg or "Failed" in error_msg
    
    def test_get_trading_symbols_fails_on_empty_instruments(self):
        """
        Test that get_trading_symbols raises ValueError if instruments is empty.
        
        CFG-STRATEGIES-SSOT-03: Fail-closed - no silent default symbols.
        """
        from apps.reference.config_symbols import get_trading_symbols
        
        # Mock get_config to return config with empty instruments
        mock_config = MagicMock()
        mock_config.instruments = {}
        
        with patch('apps.reference.config_loader.get_config', return_value=mock_config):
            with pytest.raises(ValueError) as exc_info:
                get_trading_symbols()
            
            # VERIFY: error mentions empty instruments
            error_msg = str(exc_info.value)
            assert "empty" in error_msg.lower() or "missing" in error_msg.lower()
    
    def test_get_symbol_config_uses_only_get_config(self):
        """
        Test that get_symbol_config uses ONLY get_config() (no vfoundation fallback).
        
        CFG-STRATEGIES-SSOT-03: Single source of truth for symbol configs.
        """
        from apps.reference.config_symbols import get_symbol_config
        
        # Mock get_config to return valid config
        mock_instrument = MagicMock()
        mock_instrument.model_dump.return_value = {
            "step_size": "0.001",
            "tick_size": "0.01"
        }
        
        mock_config = MagicMock()
        mock_config.instruments = {
            "BTCUSDT": mock_instrument
        }
        
        with patch('apps.reference.config_loader.get_config', return_value=mock_config):
            config = get_symbol_config("BTCUSDT")
            assert config is not None
            assert config["step_size"] == "0.001"
            assert config["tick_size"] == "0.01"
    
    def test_get_symbol_config_returns_none_for_missing_symbol(self):
        """
        Test that get_symbol_config returns None if symbol not in config (no crash).
        
        CFG-STRATEGIES-SSOT-03: Graceful handling of missing symbols.
        """
        from apps.reference.config_symbols import get_symbol_config
        
        # Mock get_config to return config without target symbol
        mock_config = MagicMock()
        mock_config.instruments = {
            "ETHUSDT": MagicMock()
        }
        
        with patch('apps.reference.config_loader.get_config', return_value=mock_config):
            config = get_symbol_config("BTCUSDT")
            assert config is None
    
    def test_validate_symbol_uses_get_trading_symbols(self):
        """
        Test that validate_symbol uses get_trading_symbols (single source).
        
        CFG-STRATEGIES-SSOT-03: Consistent symbol access across all functions.
        """
        from apps.reference.config_symbols import validate_symbol
        
        # Mock get_config
        mock_config = MagicMock()
        mock_config.instruments = {
            "BTCUSDT": MagicMock(),
            "ETHUSDT": MagicMock()
        }
        
        with patch('apps.reference.config_loader.get_config', return_value=mock_config):
            assert validate_symbol("BTCUSDT") is True
            assert validate_symbol("ETHUSDT") is True
            assert validate_symbol("SOLUSDT") is False

