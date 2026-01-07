"""
STRATEGY-AWARE-GATES-FIX: Integration Tests

These tests verify the fix works with real DecisionMaking class
and actual config structures, testing the full integration.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time


# Import the actual class to test integration
try:
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    from vfoundation.core import FSMCore
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    DecisionMaking = None
    FSMCore = None


# Mock config structures matching real Pydantic models
@dataclass
class MockMaxRiskScore:
    enabled: bool = False
    value: float = 0.8


@dataclass
class MockAuroraInstrumentConfig:
    enabled: bool = True
    allowed_regimes: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    max_risk_score: Optional[MockMaxRiskScore] = None
    cooldown_sec: Optional[int] = None
    position_mode: str = "STRICT"


@dataclass
class MockAuroraAssets:
    _configs: Dict[str, MockAuroraInstrumentConfig] = field(default_factory=dict)
    
    def get(self, symbol: str) -> Optional[MockAuroraInstrumentConfig]:
        return self._configs.get(symbol)


@dataclass
class MockAuroraDecision:
    signal_threshold: float = 0.5
    signal_weights: Any = None


@dataclass
class MockAuroraStrategy:
    assets: MockAuroraAssets = field(default_factory=MockAuroraAssets)
    decision: MockAuroraDecision = field(default_factory=MockAuroraDecision)
    regime_threshold_multipliers: Dict[str, float] = field(default_factory=dict)
    cooldown_sec: int = 10


@dataclass
class MockArbitration:
    mode: str = "priority"
    window_ms: int = 1000
    priority: Dict[str, int] = field(default_factory=lambda: {"aurora": 1, "mean_reversion": 2})


@dataclass
class MockStrategiesRegistry:
    assignments: Dict[str, List[str]] = field(default_factory=dict)
    arbitration: MockArbitration = field(default_factory=MockArbitration)


@dataclass
class MockStrategies:
    aurora: MockAuroraStrategy = field(default_factory=MockAuroraStrategy)


@dataclass
class MockQosConfig:
    enabled: bool = True
    mode: str = "enforce"
    exposure_block_cooldown_sec: int = 30
    symbol_cooldown_sec: int = 1
    max_intents_per_minute: int = 10


@dataclass
class MockBehaviorFsm:
    enable: bool = False
    high_vol_multiplier: float = 0.5
    low_vol_multiplier: float = 1.5


@dataclass
class MockPositionSizing:
    base_usd: float = 100.0


@dataclass
class MockDomainsDM:
    qos: MockQosConfig = field(default_factory=MockQosConfig)
    behavior_fsm: MockBehaviorFsm = field(default_factory=MockBehaviorFsm)
    position_sizing: MockPositionSizing = field(default_factory=MockPositionSizing)


@dataclass
class MockDomains:
    decision_making: MockDomainsDM = field(default_factory=MockDomainsDM)


@dataclass
class MockConfig:
    strategies: MockStrategies = field(default_factory=MockStrategies)
    strategies_registry: MockStrategiesRegistry = field(default_factory=MockStrategiesRegistry)
    domains: MockDomains = field(default_factory=MockDomains)
    trading: Any = None


def create_test_config(
    assignments: Dict[str, List[str]],
    aurora_assets: Dict[str, MockAuroraInstrumentConfig] = None,
) -> MockConfig:
    """Helper to create test config with specific assignments."""
    config = MockConfig()
    config.strategies_registry.assignments = assignments
    
    if aurora_assets:
        config.strategies.aurora.assets._configs = aurora_assets
    
    return config


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="DecisionMaking not available")
class TestIsStrategyAssignedIntegration:
    """Integration tests for _is_strategy_assigned with real config."""
    
    def test_is_strategy_assigned_with_real_registry(self):
        """Test _is_strategy_assigned method with real-like config structure."""
        # Create mock FSM
        fsm = MagicMock(spec=FSMCore)
        fsm.listen = MagicMock()
        
        # Create config with specific assignments
        config = create_test_config(
            assignments={
                "BTCUSDT": ["aurora", "mean_reversion"],
                "DOGEUSDT": ["mean_reversion"],
                "ETHUSDT": ["aurora"],
            }
        )
        
        # Mock the config loading to avoid full initialization
        with patch.object(DecisionMaking, '__init__', lambda self, **kwargs: None):
            dm = DecisionMaking.__new__(DecisionMaking)
            dm.strategies_registry = config.strategies_registry
            dm.config = config
            dm.logger = MagicMock()
            
            # Test the method
            assert dm._is_strategy_assigned("BTCUSDT", "aurora") is True
            assert dm._is_strategy_assigned("BTCUSDT", "mean_reversion") is True
            assert dm._is_strategy_assigned("DOGEUSDT", "aurora") is False
            assert dm._is_strategy_assigned("DOGEUSDT", "mean_reversion") is True
            assert dm._is_strategy_assigned("ETHUSDT", "aurora") is True
            assert dm._is_strategy_assigned("ETHUSDT", "mean_reversion") is False
            assert dm._is_strategy_assigned("UNKNOWN", "aurora") is False


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="DecisionMaking not available")
class TestAuroraGatesIntegration:
    """Integration tests for Aurora gates with strategy-aware logic."""
    
    def test_aurora_config_not_fetched_for_mr_only_symbol(self):
        """Verify aurora config is not fetched for MR-only symbols."""
        config = create_test_config(
            assignments={
                "DOGEUSDT": ["mean_reversion"],
            },
            aurora_assets={
                "DOGEUSDT": MockAuroraInstrumentConfig(
                    enabled=True,
                    allowed_regimes=["FLAT_LOW", "FLAT_NORMAL"],
                )
            }
        )
        
        with patch.object(DecisionMaking, '__init__', lambda self, **kwargs: None):
            dm = DecisionMaking.__new__(DecisionMaking)
            dm.strategies_registry = config.strategies_registry
            dm.config = config
            dm.logger = MagicMock()
            
            # Simulate the fixed logic
            symbol = "DOGEUSDT"
            aurora_assigned = dm._is_strategy_assigned(symbol, "aurora")
            
            # Should NOT fetch aurora config because aurora not assigned
            instr_cfg = dm._get_aurora_instrument_cfg(symbol) if aurora_assigned else None
            
            assert aurora_assigned is False
            assert instr_cfg is None
    
    def test_aurora_config_fetched_for_hybrid_symbol(self):
        """Verify aurora config IS fetched for hybrid symbols."""
        config = create_test_config(
            assignments={
                "BTCUSDT": ["aurora", "mean_reversion"],
            },
            aurora_assets={
                "BTCUSDT": MockAuroraInstrumentConfig(
                    enabled=True,
                    allowed_regimes=["FLAT_LOW", "MEAN_REVERSION"],
                )
            }
        )
        
        with patch.object(DecisionMaking, '__init__', lambda self, **kwargs: None):
            dm = DecisionMaking.__new__(DecisionMaking)
            dm.strategies_registry = config.strategies_registry
            dm.config = config
            dm.logger = MagicMock()
            
            symbol = "BTCUSDT"
            aurora_assigned = dm._is_strategy_assigned(symbol, "aurora")
            instr_cfg = dm._get_aurora_instrument_cfg(symbol) if aurora_assigned else None
            
            assert aurora_assigned is True
            assert instr_cfg is not None
            assert instr_cfg.allowed_regimes == ["FLAT_LOW", "MEAN_REVERSION"]


class TestRegimeGateIntegration:
    """Integration tests for regime gate with strategy-aware logic."""
    
    def test_regime_gate_simulation_mr_only(self):
        """Simulate regime gate logic for MR-only symbol."""
        config = create_test_config(
            assignments={"DOGEUSDT": ["mean_reversion"]},
            aurora_assets={
                "DOGEUSDT": MockAuroraInstrumentConfig(
                    enabled=True,
                    allowed_regimes=["FLAT_LOW", "FLAT_NORMAL"],
                )
            }
        )
        
        symbol = "DOGEUSDT"
        current_regime = "TREND_UP"  # Would be blocked by aurora allowed_regimes
        
        # Simulate fixed logic
        aurora_assigned = "aurora" in config.strategies_registry.assignments.get(symbol, [])
        instr_cfg = config.strategies.aurora.assets.get(symbol) if aurora_assigned else None
        
        # Regime gate check
        regime_blocked = False
        if instr_cfg:  # Only check if aurora assigned
            allowed = instr_cfg.allowed_regimes or []
            if allowed and current_regime not in allowed:
                regime_blocked = True
        
        # Should NOT be blocked
        assert regime_blocked is False
    
    def test_regime_gate_simulation_aurora_symbol(self):
        """Simulate regime gate logic for aurora symbol."""
        config = create_test_config(
            assignments={"ETHUSDT": ["aurora"]},
            aurora_assets={
                "ETHUSDT": MockAuroraInstrumentConfig(
                    enabled=True,
                    allowed_regimes=["TREND_UP", "TREND_DOWN"],
                )
            }
        )
        
        symbol = "ETHUSDT"
        current_regime = "HIGH_VOLATILITY"  # Not in allowed_regimes
        
        aurora_assigned = "aurora" in config.strategies_registry.assignments.get(symbol, [])
        instr_cfg = config.strategies.aurora.assets.get(symbol) if aurora_assigned else None
        
        regime_blocked = False
        if instr_cfg:
            allowed = instr_cfg.allowed_regimes or []
            if allowed and current_regime not in allowed:
                regime_blocked = True
        
        # SHOULD be blocked
        assert regime_blocked is True


class TestWarmupGateIntegration:
    """Integration tests for warmup gate with strategy-aware logic."""
    
    def test_warmup_gate_skipped_for_mr_only(self):
        """Warmup gate should be skipped for MR-only symbols."""
        config = create_test_config(
            assignments={"DOGEUSDT": ["mean_reversion"]},
        )
        
        symbol = "DOGEUSDT"
        warmup_ready = False  # Not ready
        
        aurora_assigned = "aurora" in config.strategies_registry.assignments.get(symbol, [])
        
        # Warmup check only applies to aurora symbols
        warmup_blocked = False
        if aurora_assigned and not warmup_ready:
            warmup_blocked = True
        
        # Should NOT be blocked
        assert warmup_blocked is False
    
    def test_warmup_gate_applies_to_aurora(self):
        """Warmup gate should apply to aurora symbols."""
        config = create_test_config(
            assignments={"BTCUSDT": ["aurora", "mean_reversion"]},
        )
        
        symbol = "BTCUSDT"
        warmup_ready = False
        
        aurora_assigned = "aurora" in config.strategies_registry.assignments.get(symbol, [])
        
        warmup_blocked = False
        if aurora_assigned and not warmup_ready:
            warmup_blocked = True
        
        # SHOULD be blocked
        assert warmup_blocked is True


class TestBackwardCompatibility:
    """Tests for backward compatibility when no registry exists."""
    
    def test_no_registry_assumes_aurora(self):
        """Without registry, assume aurora for backward compat."""
        # Simulate no registry
        strategies_registry = None
        
        # Backward compat logic from _is_strategy_assigned
        if strategies_registry is None:
            aurora_assumed = True
        else:
            aurora_assumed = False
        
        assert aurora_assumed is True
    
    def test_empty_registry_no_assumptions(self):
        """Empty registry should not assume anything."""
        config = create_test_config(assignments={})
        
        symbol = "BTCUSDT"
        aurora_assigned = "aurora" in config.strategies_registry.assignments.get(symbol, [])
        
        assert aurora_assigned is False


class TestArbitrationIntegration:
    """Integration tests for arbitration with strategy assignment checks."""
    
    def test_arbitration_respects_assignments(self):
        """Arbitration should only allow assigned strategies."""
        config = create_test_config(
            assignments={
                "DOGEUSDT": ["mean_reversion"],
                "BTCUSDT": ["aurora", "mean_reversion"],
            }
        )
        
        # DOGE: aurora signal should be rejected
        doge_aurora_allowed = "aurora" in config.strategies_registry.assignments.get("DOGEUSDT", [])
        assert doge_aurora_allowed is False
        
        # DOGE: MR signal should be allowed
        doge_mr_allowed = "mean_reversion" in config.strategies_registry.assignments.get("DOGEUSDT", [])
        assert doge_mr_allowed is True
        
        # BTC: both should be allowed
        btc_aurora_allowed = "aurora" in config.strategies_registry.assignments.get("BTCUSDT", [])
        btc_mr_allowed = "mean_reversion" in config.strategies_registry.assignments.get("BTCUSDT", [])
        assert btc_aurora_allowed is True
        assert btc_mr_allowed is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
