"""
Tests for Mean Reversion Handler integration in DecisionMaking.

Track B: Tests for MR 1m strategy integration.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any

from apps.reference.config_models import (
    MeanReversion1mStrategyConfig,
    MRStrategyParamsConfig,
    MRAssetConfig,
    MRRiskConfig,
)
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler


class MockFSM:
    """Mock FSM for testing."""
    
    def __init__(self):
        self.listeners: Dict[str, list] = {}
        self.emitted_events: list = []
    
    def listen(self, event_type: str, handler):
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(handler)
    
    def emit(self, event_type: str, **kwargs):
        self.emitted_events.append({
            "event_type": event_type,
            **kwargs
        })


def create_mr_config(enabled: bool = True, symbols: list = None) -> Dict[str, Any]:
    """Create a mock MR config dict."""
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT"]
    
    return {
        "mean_reversion_1m": {
            "enabled": enabled,
            "timeframe_sec": 60,
            "strategy": {
                "bb_window": 20,
                "bb_num_std": 2.0,
                "atr_window": 14,
                "rsi_window": 14,
                "min_bars": 25,
                "min_bb_width": 0.001,
                "max_bb_width": 0.05,
                "entry_threshold": 0.05,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "sl_atr_mult": 1.5,
                "tp_to_mid": True,
                "cooldown_sec": 60,
            },
            "assets": {
                symbol: {
                    "enabled": True,
                    "bb_window": 20,
                    "sl_pct": 0.01,
                    "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
                }
                for symbol in symbols
            },
            "risk": {
                "position_size_usd": 100.0,
            },
        }
    }


class TestMeanReversionHandlerInit:
    """Tests for MeanReversionHandler initialization."""
    
    def test_init_with_enabled_config(self):
        """Handler initializes correctly when enabled."""
        fsm = MockFSM()
        config = create_mr_config(enabled=True, symbols=["BTCUSDT"])
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        assert handler.enabled is True
        assert "BTCUSDT" in handler._enabled_symbols
    
    def test_init_with_disabled_config(self):
        """Handler is disabled when config says so."""
        fsm = MockFSM()
        config = create_mr_config(enabled=False)
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        assert handler.enabled is False
        assert len(handler._enabled_symbols) == 0
    
    def test_init_with_no_mr_config(self):
        """Handler is disabled when no MR config present."""
        fsm = MockFSM()
        config = {}  # No mean_reversion_1m key
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        assert handler.enabled is False
    
    def test_init_with_no_enabled_symbols(self):
        """Handler is disabled when no symbols are enabled."""
        fsm = MockFSM()
        config = {
            "mean_reversion_1m": {
                "enabled": True,
                "strategy": {"bb_window": 20},
                "assets": {
                    "BTCUSDT": {"enabled": False},  # Disabled
                },
            }
        }
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        assert handler.enabled is False
    
    def test_is_symbol_enabled(self):
        """Test is_symbol_enabled method."""
        fsm = MockFSM()
        config = create_mr_config(enabled=True, symbols=["BTCUSDT"])
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        assert handler.is_symbol_enabled("BTCUSDT") is True
        assert handler.is_symbol_enabled("ETHUSDT") is False
        assert handler.is_symbol_enabled("XRPUSDT") is False


class TestMeanReversionHandlerOnTick:
    """Tests for MeanReversionHandler.on_tick()."""
    
    def test_on_tick_returns_none_when_disabled(self):
        """on_tick returns None when handler is disabled."""
        fsm = MockFSM()
        config = create_mr_config(enabled=False)
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        result = handler.on_tick(
            symbol="BTCUSDT",
            price=Decimal("50000"),
            volume=Decimal("1"),
            timestamp_ms=1000,
        )
        
        assert result is None
    
    def test_on_tick_returns_none_for_disabled_symbol(self):
        """on_tick returns None for non-enabled symbol."""
        fsm = MockFSM()
        config = create_mr_config(enabled=True, symbols=["BTCUSDT"])
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        result = handler.on_tick(
            symbol="XRPUSDT",  # Not in enabled symbols
            price=Decimal("1"),
            volume=Decimal("100"),
            timestamp_ms=1000,
        )
        
        assert result is None
    
    def test_on_tick_processes_enabled_symbol(self):
        """on_tick processes ticks for enabled symbol."""
        fsm = MockFSM()
        config = create_mr_config(enabled=True, symbols=["BTCUSDT"])
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        # First tick shouldn't complete a bar
        result = handler.on_tick(
            symbol="BTCUSDT",
            price=Decimal("50000"),
            volume=Decimal("1"),
            timestamp_ms=1000,
        )
        
        # May return None (bar not complete) or MRSignal (neutral)
        # Just ensure no exception
        assert result is None or hasattr(result, 'signal_type')


class TestMeanReversionHandlerOnRegime:
    """Tests for MeanReversionHandler.on_regime()."""
    
    def test_on_regime_updates_strategy(self):
        """on_regime updates the strategy's regime for symbol."""
        fsm = MockFSM()
        config = create_mr_config(enabled=True, symbols=["BTCUSDT"])
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        handler.on_regime("BTCUSDT", "MEAN_REVERSION")
        
        assert handler._strategy.get_regime("BTCUSDT") == "MEAN_REVERSION"
    
    def test_on_regime_ignored_when_disabled(self):
        """on_regime does nothing when handler is disabled."""
        fsm = MockFSM()
        config = create_mr_config(enabled=False)
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        # Should not raise
        handler.on_regime("BTCUSDT", "MEAN_REVERSION")


class TestMeanReversionHandlerStats:
    """Tests for MeanReversionHandler statistics."""
    
    def test_get_stats_returns_dict(self):
        """get_stats returns a dict with expected keys."""
        fsm = MockFSM()
        config = create_mr_config(enabled=True, symbols=["BTCUSDT"])
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        stats = handler.get_stats()
        
        assert isinstance(stats, dict)
        assert "enabled" in stats
        assert "enabled_symbols" in stats
        assert "signal_counts" in stats
        assert stats["enabled"] is True
        assert "BTCUSDT" in stats["enabled_symbols"]


class TestMeanReversionHandlerReset:
    """Tests for MeanReversionHandler reset methods."""
    
    def test_reset_symbol(self):
        """reset_symbol clears state for symbol."""
        fsm = MockFSM()
        config = create_mr_config(enabled=True, symbols=["BTCUSDT"])
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        # Add some state
        handler._signal_counts["BTCUSDT"] = 5
        
        handler.reset_symbol("BTCUSDT")
        
        assert "BTCUSDT" not in handler._signal_counts
    
    def test_reset_all(self):
        """reset_all clears all state."""
        fsm = MockFSM()
        config = create_mr_config(enabled=True, symbols=["BTCUSDT", "ETHUSDT"])
        dm = Mock()
        
        handler = MeanReversionHandler(fsm=fsm, config=config, decision_making=dm)
        
        # Add some state
        handler._signal_counts["BTCUSDT"] = 5
        handler._signal_counts["ETHUSDT"] = 3
        
        handler.reset_all()
        
        assert len(handler._signal_counts) == 0


class TestMeanReversionConfigModels:
    """Tests for MR 1m Pydantic config models."""
    
    def test_mr_strategy_params_defaults(self):
        """MRStrategyParamsConfig has correct defaults."""
        config = MRStrategyParamsConfig()
        
        assert config.bb_window == 20
        assert config.bb_num_std == 2.0
        assert config.entry_threshold == 0.05
        assert config.cooldown_sec == 60
    
    def test_mr_asset_config(self):
        """MRAssetConfig parses correctly."""
        config = MRAssetConfig(
            enabled=True,
            bb_window=25,
            sl_pct=0.0068,
        )
        
        assert config.enabled is True
        assert config.bb_window == 25
        assert config.sl_pct == 0.0068
    
    def test_mean_reversion_1m_strategy_config(self):
        """MeanReversion1mStrategyConfig parses full config."""
        config = MeanReversion1mStrategyConfig(
            enabled=True,
            timeframe_sec=60,
            strategy=MRStrategyParamsConfig(bb_window=30),
            assets={
                "BTCUSDT": MRAssetConfig(enabled=True, sl_pct=0.01),
            },
            risk=MRRiskConfig(position_size_usd=200),
        )
        
        assert config.enabled is True
        assert config.timeframe_sec == 60
        assert config.strategy.bb_window == 30
        assert "BTCUSDT" in config.assets
        assert config.assets["BTCUSDT"].sl_pct == 0.01
        assert config.risk.position_size_usd == 200
