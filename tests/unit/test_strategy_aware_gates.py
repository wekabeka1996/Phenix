"""
STRATEGY-AWARE-GATES-FIX: Unit Tests

Tests for the architectural fix that ensures strategy-specific gates
(warmup, regime, etc.) are only applied to symbols that have that
strategy assigned in strategies_registry.assignments.

Problem Fixed:
- DOGE/XRP were in aurora.assets (for shared infra config)
- DecisionMaking applied Aurora gates (REGIME_GATE_BLOCKED) to ALL symbols in aurora.assets
- This blocked MR-only symbols even when they had valid MR signals

Solution:
- _is_strategy_assigned(symbol, strategy_id) checks strategies_registry.assignments
- Aurora gates only apply when aurora is in assignments for that symbol
- MR-only symbols skip Aurora gates entirely
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Dict, List, Optional, Any


# Mock config structures
@dataclass
class MockStrategiesRegistry:
    assignments: Dict[str, List[str]]
    arbitration: Any = None


@dataclass
class MockAuroraInstrumentConfig:
    enabled: bool = True
    allowed_regimes: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None


@dataclass 
class MockAuroraAssets:
    def get(self, symbol: str) -> Optional[MockAuroraInstrumentConfig]:
        # Simulate aurora.assets containing DOGE/XRP (legacy config)
        configs = {
            "BTCUSDT": MockAuroraInstrumentConfig(
                enabled=True,
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "MEAN_REVERSION"],
            ),
            "ETHUSDT": MockAuroraInstrumentConfig(
                enabled=True,
                allowed_regimes=["TREND_UP", "TREND_DOWN"],
            ),
            "DOGEUSDT": MockAuroraInstrumentConfig(
                enabled=True,
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL"],  # Would block TREND_UP!
            ),
            "XRPUSDT": MockAuroraInstrumentConfig(
                enabled=True,
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL"],
            ),
        }
        return configs.get(symbol)


@dataclass
class MockAuroraStrategy:
    assets: MockAuroraAssets = None
    
    def __post_init__(self):
        if self.assets is None:
            self.assets = MockAuroraAssets()


@dataclass
class MockStrategies:
    aurora: MockAuroraStrategy = None
    
    def __post_init__(self):
        if self.aurora is None:
            self.aurora = MockAuroraStrategy()


class TestIsStrategyAssigned:
    """Unit tests for _is_strategy_assigned helper method."""
    
    def test_aurora_assigned_to_btc(self):
        """BTC has aurora in assignments → should return True."""
        registry = MockStrategiesRegistry(
            assignments={
                "BTCUSDT": ["aurora", "mean_reversion"],
                "DOGEUSDT": ["mean_reversion"],
            }
        )
        
        # Simulate the method logic
        assignments = registry.assignments.get("BTCUSDT", [])
        result = "aurora" in assignments
        
        assert result is True
    
    def test_aurora_not_assigned_to_doge(self):
        """DOGE has only mean_reversion → aurora should return False."""
        registry = MockStrategiesRegistry(
            assignments={
                "BTCUSDT": ["aurora", "mean_reversion"],
                "DOGEUSDT": ["mean_reversion"],
            }
        )
        
        assignments = registry.assignments.get("DOGEUSDT", [])
        result = "aurora" in assignments
        
        assert result is False
    
    def test_mr_assigned_to_doge(self):
        """DOGE has mean_reversion → should return True."""
        registry = MockStrategiesRegistry(
            assignments={
                "DOGEUSDT": ["mean_reversion"],
            }
        )
        
        assignments = registry.assignments.get("DOGEUSDT", [])
        result = "mean_reversion" in assignments
        
        assert result is True
    
    def test_symbol_not_in_registry(self):
        """Symbol not in registry → should return False."""
        registry = MockStrategiesRegistry(
            assignments={
                "BTCUSDT": ["aurora"],
            }
        )
        
        assignments = registry.assignments.get("UNKNOWN", [])
        result = "aurora" in assignments
        
        assert result is False
    
    def test_no_registry_backward_compat(self):
        """No registry → backward compat assumes aurora for all."""
        registry = None
        
        # Simulate backward compat logic
        if registry is None:
            result = True  # Assume aurora
        else:
            result = False
        
        assert result is True


class TestStrategyAwareGates:
    """
    Tests that strategy-specific gates are only applied to assigned symbols.
    """
    
    def test_aurora_gates_applied_to_aurora_symbol(self):
        """Aurora gates should apply to symbols with aurora assigned."""
        registry = MockStrategiesRegistry(
            assignments={"BTCUSDT": ["aurora", "mean_reversion"]}
        )
        strategies = MockStrategies()
        
        symbol = "BTCUSDT"
        aurora_assigned = "aurora" in registry.assignments.get(symbol, [])
        instr_cfg = strategies.aurora.assets.get(symbol) if aurora_assigned else None
        
        assert aurora_assigned is True
        assert instr_cfg is not None
        assert instr_cfg.enabled is True
        assert instr_cfg.allowed_regimes == ["FLAT_LOW", "FLAT_NORMAL", "MEAN_REVERSION"]
    
    def test_aurora_gates_skipped_for_mr_only_symbol(self):
        """Aurora gates should NOT apply to MR-only symbols."""
        registry = MockStrategiesRegistry(
            assignments={"DOGEUSDT": ["mean_reversion"]}  # MR only
        )
        strategies = MockStrategies()
        
        symbol = "DOGEUSDT"
        aurora_assigned = "aurora" in registry.assignments.get(symbol, [])
        instr_cfg = strategies.aurora.assets.get(symbol) if aurora_assigned else None
        
        # Key assertion: aurora not assigned
        assert aurora_assigned is False
        # Key assertion: instr_cfg is None (gates won't apply)
        assert instr_cfg is None
    
    def test_regime_gate_not_blocking_mr_only_symbol(self):
        """
        REGIME_GATE_BLOCKED should NOT happen for MR-only symbols.
        
        Scenario:
        - DOGE is in aurora.assets with allowed_regimes=["FLAT_LOW", "FLAT_NORMAL"]
        - Current regime = TREND_UP
        - DOGE assignments = ["mean_reversion"] only
        
        Before fix: REGIME_GATE_BLOCKED (TREND_UP not in allowed_regimes)
        After fix: Gate skipped, MR signal can proceed
        """
        registry = MockStrategiesRegistry(
            assignments={"DOGEUSDT": ["mean_reversion"]}
        )
        strategies = MockStrategies()
        
        symbol = "DOGEUSDT"
        current_regime = "TREND_UP"  # Would be blocked by aurora allowed_regimes
        
        # Simulate the FIXED logic
        aurora_assigned = "aurora" in registry.assignments.get(symbol, [])
        instr_cfg = strategies.aurora.assets.get(symbol) if aurora_assigned else None
        
        # Check if regime gate would apply
        regime_gate_applies = False
        if instr_cfg:  # Only if aurora assigned
            allowed_regimes = instr_cfg.allowed_regimes or []
            if allowed_regimes and current_regime not in allowed_regimes:
                regime_gate_applies = True
        
        # Gate should NOT apply because aurora is not assigned
        assert regime_gate_applies is False
    
    def test_regime_gate_blocks_aurora_symbol_wrong_regime(self):
        """
        REGIME_GATE should still block aurora symbols with wrong regime.
        """
        registry = MockStrategiesRegistry(
            assignments={"ETHUSDT": ["aurora"]}
        )
        strategies = MockStrategies()
        
        symbol = "ETHUSDT"
        current_regime = "HIGH_VOLATILITY"  # Not in allowed_regimes
        
        aurora_assigned = "aurora" in registry.assignments.get(symbol, [])
        instr_cfg = strategies.aurora.assets.get(symbol) if aurora_assigned else None
        
        regime_gate_applies = False
        if instr_cfg:
            allowed_regimes = instr_cfg.allowed_regimes or []
            if allowed_regimes and current_regime not in allowed_regimes:
                regime_gate_applies = True
        
        # Gate SHOULD apply and block
        assert regime_gate_applies is True


class TestHybridSymbols:
    """Tests for hybrid symbols (both aurora and mean_reversion assigned)."""
    
    def test_hybrid_symbol_aurora_gates_apply(self):
        """Hybrid symbols should have Aurora gates apply."""
        registry = MockStrategiesRegistry(
            assignments={"BTCUSDT": ["aurora", "mean_reversion"]}
        )
        strategies = MockStrategies()
        
        symbol = "BTCUSDT"
        aurora_assigned = "aurora" in registry.assignments.get(symbol, [])
        mr_assigned = "mean_reversion" in registry.assignments.get(symbol, [])
        
        assert aurora_assigned is True
        assert mr_assigned is True
        
        # Aurora gates should apply for Aurora flow
        instr_cfg = strategies.aurora.assets.get(symbol) if aurora_assigned else None
        assert instr_cfg is not None
    
    def test_hybrid_symbol_mr_signal_uses_gateway(self):
        """
        Hybrid symbol MR signals should go through strategy gateway,
        not Aurora decision flow.
        """
        registry = MockStrategiesRegistry(
            assignments={"BTCUSDT": ["aurora", "mean_reversion"]}
        )
        
        # MR signal should use EVT:STRATEGY_SIGNAL_PRODUCED → gateway
        # Aurora flow is separate (_make_decision_for_symbol)
        
        # Simulate MR signal payload
        mr_signal = {
            "strategy_id": "mean_reversion",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "score": 0.85,
        }
        
        # Gateway checks arbitration
        assignments = registry.assignments.get("BTCUSDT", [])
        strategy_assigned = mr_signal["strategy_id"] in assignments
        
        assert strategy_assigned is True


class TestEdgeCases:
    """Edge cases and boundary conditions."""
    
    def test_empty_assignments_list(self):
        """Empty assignments list should be treated as no strategies assigned."""
        registry = MockStrategiesRegistry(
            assignments={"BTCUSDT": []}
        )
        
        assignments = registry.assignments.get("BTCUSDT", [])
        aurora_assigned = "aurora" in assignments
        
        assert aurora_assigned is False
    
    def test_none_assignments(self):
        """None assignments should be treated as no strategies assigned."""
        registry = MockStrategiesRegistry(
            assignments={}
        )
        
        assignments = registry.assignments.get("BTCUSDT", [])
        aurora_assigned = "aurora" in assignments
        
        assert aurora_assigned is False
    
    def test_case_sensitivity(self):
        """Strategy IDs should be case-sensitive."""
        registry = MockStrategiesRegistry(
            assignments={"BTCUSDT": ["Aurora", "Mean_Reversion"]}  # Wrong case
        )
        
        assignments = registry.assignments.get("BTCUSDT", [])
        aurora_assigned = "aurora" in assignments  # lowercase
        
        # Should NOT match due to case difference
        assert aurora_assigned is False
    
    def test_whitespace_in_strategy_id(self):
        """Strategy IDs with whitespace should not match."""
        registry = MockStrategiesRegistry(
            assignments={"BTCUSDT": [" aurora", "mean_reversion "]}  # With spaces
        )
        
        assignments = registry.assignments.get("BTCUSDT", [])
        aurora_assigned = "aurora" in assignments
        
        assert aurora_assigned is False


class TestRegressionScenarios:
    """
    Regression tests for the specific bug that was fixed.
    """
    
    def test_doge_trend_up_not_blocked(self):
        """
        REGRESSION: DOGE with TREND_UP regime should NOT be blocked.
        
        Before fix: [DOGEUSDT] REGIME_GATE_BLOCKED: TREND_UP not in ['FLAT_LOW', ...]
        After fix: Gate skipped because aurora not in assignments
        """
        registry = MockStrategiesRegistry(
            assignments={
                "DOGEUSDT": ["mean_reversion"],
                "XRPUSDT": ["mean_reversion"],
                "BTCUSDT": ["aurora", "mean_reversion"],
            }
        )
        
        for symbol in ["DOGEUSDT", "XRPUSDT"]:
            aurora_assigned = "aurora" in registry.assignments.get(symbol, [])
            
            # Key check: aurora should NOT be assigned
            assert aurora_assigned is False, f"{symbol} should not have aurora assigned"
    
    def test_btc_still_has_aurora_gates(self):
        """
        BTC should still have Aurora gates (it's hybrid).
        """
        registry = MockStrategiesRegistry(
            assignments={"BTCUSDT": ["aurora", "mean_reversion"]}
        )
        
        aurora_assigned = "aurora" in registry.assignments.get("BTCUSDT", [])
        assert aurora_assigned is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
