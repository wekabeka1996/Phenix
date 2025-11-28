"""
Unit Tests for Adapter Factory.

Tests that all supported trading modes correctly create BinanceAdapter,
and unknown modes return None (safe fallback).
"""
import pytest
from unittest.mock import MagicMock, patch

from apps.reference.domains.execution_position.infra.adapter_factory import (
    build_execution_adapter,
    _extract_trading_mode,
    _SUPPORTED_MODES,
    CANONICAL_EXECUTION_ADAPTER,
)
from apps.reference.adapters.binance_adapter import BinanceAdapter


class TestExtractTradingMode:
    """Tests for _extract_trading_mode helper."""

    def test_extract_from_attribute(self):
        """Extract trading_mode from object attribute."""
        class Config:
            trading_mode = "live"

        assert _extract_trading_mode(Config()) == "live"

    def test_extract_from_dict_trading_section(self):
        """Extract from dict['trading']['trading_mode']."""
        config = {"trading": {"trading_mode": "testnet"}}
        assert _extract_trading_mode(config) == "testnet"

    def test_extract_from_dict_mode_key(self):
        """Extract from dict['trading']['mode']."""
        config = {"trading": {"mode": "shadow_live"}}
        assert _extract_trading_mode(config) == "shadow_live"

    def test_fallback_to_testnet(self):
        """Default to 'testnet' when no mode found."""
        assert _extract_trading_mode({}) == "testnet"
        assert _extract_trading_mode(None) == "testnet"

    def test_case_insensitive(self):
        """Mode extraction is case-insensitive."""
        class Config:
            trading_mode = "LIVE"

        assert _extract_trading_mode(Config()) == "live"

    def test_to_dict_method(self):
        """Extract from object with to_dict() method."""
        class Config:
            def to_dict(self):
                return {"trading": {"trading_mode": "full_live"}}

        assert _extract_trading_mode(Config()) == "full_live"


class TestSupportedModes:
    """Tests for _SUPPORTED_MODES constant."""

    def test_contains_all_standard_modes(self):
        """All standard trading modes are supported."""
        expected = {
            "testnet",
            "live",
            "hybrid_live_data_testnet_exec",
            "shadow_live",
            "full_live",
            "full_testnet",
        }
        assert expected == _SUPPORTED_MODES

    def test_is_frozenset(self):
        """_SUPPORTED_MODES is immutable."""
        assert isinstance(_SUPPORTED_MODES, frozenset)


class TestBuildExecutionAdapter:
    """Tests for build_execution_adapter factory function."""

    @pytest.mark.parametrize("mode", [
        "testnet",
        "live",
        "hybrid_live_data_testnet_exec",
        "shadow_live",
        "full_live",
        "full_testnet",
    ])
    def test_supported_modes_create_adapter(self, mode):
        """All supported modes should create BinanceAdapter."""
        config = MagicMock()
        config.trading_mode = mode

        with patch.object(BinanceAdapter, '__init__', return_value=None):
            adapter = build_execution_adapter(config, fsm=None)
            assert adapter is not None

    def test_unknown_mode_returns_none(self):
        """Unknown trading mode returns None (safe fallback)."""
        config = MagicMock()
        config.trading_mode = "unknown_mode"

        adapter = build_execution_adapter(config, fsm=None)
        assert adapter is None

    def test_sim_mode_returns_none(self):
        """Simulation mode (removed) returns None."""
        config = MagicMock()
        config.trading_mode = "sim"

        adapter = build_execution_adapter(config, fsm=None)
        assert adapter is None

    def test_paper_mode_returns_none(self):
        """Paper mode (removed) returns None."""
        config = MagicMock()
        config.trading_mode = "paper"

        adapter = build_execution_adapter(config, fsm=None)
        assert adapter is None

    def test_fsm_passed_to_adapter(self):
        """FSM is passed to adapter constructor."""
        config = MagicMock()
        config.trading_mode = "testnet"
        fsm = MagicMock()

        with patch.object(BinanceAdapter, '__init__', return_value=None) as mock_init:
            build_execution_adapter(config, fsm=fsm)
            mock_init.assert_called_once_with(config=config, fsm=fsm)

    def test_canonical_adapter_is_binance(self):
        """CANONICAL_EXECUTION_ADAPTER is BinanceAdapter."""
        assert CANONICAL_EXECUTION_ADAPTER is BinanceAdapter
