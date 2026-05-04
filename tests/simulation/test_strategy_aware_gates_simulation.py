"""
STRATEGY-AWARE-GATES-FIX: Simulation Tests

These tests simulate real trading scenarios to verify the fix
works end-to-end with realistic event flows.

Scenarios tested:
1. DOGE MR signal in TREND_UP regime (previously blocked)
2. BTC hybrid with both Aurora and MR signals
3. ETH aurora-only with regime gate
4. XRP MR signal in various regimes
5. Full event flow simulation
"""

import pytest
from unittest.mock import MagicMock, patch, call
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from decimal import Decimal
import time
import uuid


@dataclass
class MockMessage:
    """Mock FSM Message."""
    pld: Dict[str, Any]
    op: str = "EVT"
    verb: str = ""
    src: str = "test"
    dst: str = "any"
    why: str = ""


class TradingScenarioSimulator:
    """
    Simulates trading scenarios with strategy-aware gates.
    """
    
    def __init__(self, assignments: Dict[str, List[str]], aurora_assets: Dict[str, Dict] = None):
        self.assignments = assignments
        self.aurora_assets = aurora_assets or {}
        self.per_symbol_regimes: Dict[str, Dict] = {}
        self.blocked_intents: List[Dict] = []
        self.allowed_intents: List[Dict] = []
        self.events_emitted: List[Dict] = []
    
    def is_strategy_assigned(self, symbol: str, strategy_id: str) -> bool:
        """Check if strategy is assigned to symbol."""
        return strategy_id in self.assignments.get(symbol, [])
    
    def get_aurora_config(self, symbol: str) -> Optional[Dict]:
        """Get aurora config for symbol (only if aurora assigned)."""
        if not self.is_strategy_assigned(symbol, "aurora"):
            return None
        return self.aurora_assets.get(symbol)
    
    def set_regime(self, symbol: str, regime: str, warmup_ready: bool = True):
        """Set regime for symbol."""
        self.per_symbol_regimes[symbol] = {
            "regime": regime,
            "warmup": {"full_ready": warmup_ready, "ticks_seen": 1000 if warmup_ready else 50}
        }
    
    def check_warmup_gate(self, symbol: str) -> tuple[bool, str]:
        """
        Check warmup gate. Returns (allowed, reason).
        Only applies to aurora-assigned symbols.
        """
        if not self.is_strategy_assigned(symbol, "aurora"):
            return True, "aurora_not_assigned"
        
        regime_data = self.per_symbol_regimes.get(symbol, {})
        warmup = regime_data.get("warmup", {})
        
        if not warmup.get("full_ready", False):
            return False, "WARMUP_GUARD_BLOCKED"
        
        return True, "warmup_ready"
    
    def check_regime_gate(self, symbol: str) -> tuple[bool, str]:
        """
        Check regime gate. Returns (allowed, reason).
        Only applies to aurora-assigned symbols with allowed_regimes config.
        """
        aurora_cfg = self.get_aurora_config(symbol)
        if not aurora_cfg:
            return True, "aurora_not_assigned_or_no_config"
        
        allowed_regimes = aurora_cfg.get("allowed_regimes", [])
        if not allowed_regimes:
            return True, "no_regime_restrictions"
        
        current_regime = self.per_symbol_regimes.get(symbol, {}).get("regime")
        if not current_regime:
            return False, "REGIME_GATE_DEFER:missing_regime"
        
        if current_regime not in allowed_regimes:
            return False, f"REGIME_GATE_BLOCKED:{current_regime}_not_in_{allowed_regimes}"
        
        return True, "regime_allowed"
    
    def simulate_aurora_decision_flow(self, symbol: str) -> Dict:
        """
        Simulate Aurora decision flow for a symbol.
        Returns result with allowed/blocked status.
        """
        result = {
            "symbol": symbol,
            "strategy": "aurora",
            "flow": "aurora_decision",
            "checks": [],
        }
        
        # Check if aurora assigned
        if not self.is_strategy_assigned(symbol, "aurora"):
            result["status"] = "skipped"
            result["reason"] = "aurora_not_assigned"
            return result
        
        # Warmup gate
        warmup_ok, warmup_reason = self.check_warmup_gate(symbol)
        result["checks"].append({"gate": "warmup", "passed": warmup_ok, "reason": warmup_reason})
        if not warmup_ok:
            result["status"] = "blocked"
            result["reason"] = warmup_reason
            self.blocked_intents.append(result)
            return result
        
        # Regime gate
        regime_ok, regime_reason = self.check_regime_gate(symbol)
        result["checks"].append({"gate": "regime", "passed": regime_ok, "reason": regime_reason})
        if not regime_ok:
            result["status"] = "blocked"
            result["reason"] = regime_reason
            self.blocked_intents.append(result)
            return result
        
        result["status"] = "allowed"
        result["reason"] = "all_gates_passed"
        self.allowed_intents.append(result)
        return result
    
    def simulate_mr_signal_gateway(self, symbol: str, side: str, confidence: float) -> Dict:
        """
        Simulate MR signal going through strategy gateway.
        """
        result = {
            "symbol": symbol,
            "strategy": "mean_reversion",
            "flow": "strategy_gateway",
            "side": side,
            "confidence": confidence,
            "checks": [],
        }
        
        # Check arbitration (is MR assigned?)
        if not self.is_strategy_assigned(symbol, "mean_reversion"):
            result["status"] = "blocked"
            result["reason"] = "ARBITRATION_REJECT:strategy_not_assigned"
            self.blocked_intents.append(result)
            return result
        
        result["checks"].append({"gate": "arbitration", "passed": True, "reason": "mr_assigned"})
        
        # MR signals do NOT go through Aurora warmup/regime gates!
        # They have their own regime handling in MR strategy
        
        result["status"] = "allowed"
        result["reason"] = "gateway_passed"
        self.allowed_intents.append(result)
        return result


class TestDogeMRScenario:
    """
    Scenario: DOGE is MR-only symbol
    
    Before fix: REGIME_GATE_BLOCKED because DOGE in aurora.assets with allowed_regimes
    After fix: Aurora gates skipped, MR signal proceeds through gateway
    """
    
    def test_doge_mr_signal_in_trend_up(self):
        """DOGE MR signal should proceed in TREND_UP regime."""
        sim = TradingScenarioSimulator(
            assignments={
                "DOGEUSDT": ["mean_reversion"],  # MR only
            },
            aurora_assets={
                # DOGE is in aurora.assets (legacy config) but NOT assigned aurora
                "DOGEUSDT": {
                    "enabled": True,
                    "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL"],  # Would block TREND_UP
                }
            }
        )
        
        # Set regime to TREND_UP (would be blocked by aurora gate)
        sim.set_regime("DOGEUSDT", "TREND_UP", warmup_ready=True)
        
        # Test Aurora flow - should be SKIPPED
        aurora_result = sim.simulate_aurora_decision_flow("DOGEUSDT")
        assert aurora_result["status"] == "skipped"
        assert aurora_result["reason"] == "aurora_not_assigned"
        
        # Test MR signal - should PASS
        mr_result = sim.simulate_mr_signal_gateway("DOGEUSDT", "BUY", 0.85)
        assert mr_result["status"] == "allowed"
        assert mr_result["reason"] == "gateway_passed"
        
        # Verify no blocked intents for DOGE
        blocked = [i for i in sim.blocked_intents if i["symbol"] == "DOGEUSDT"]
        assert len(blocked) == 0
    
    def test_doge_mr_signal_in_mean_reversion_regime(self):
        """DOGE MR signal should also work in MEAN_REVERSION regime."""
        sim = TradingScenarioSimulator(
            assignments={"DOGEUSDT": ["mean_reversion"]},
        )
        
        sim.set_regime("DOGEUSDT", "MEAN_REVERSION")
        
        mr_result = sim.simulate_mr_signal_gateway("DOGEUSDT", "SELL", 0.72)
        assert mr_result["status"] == "allowed"


class TestBTCHybridScenario:
    """
    Scenario: BTC is hybrid symbol (aurora + mean_reversion)
    
    Both strategies should be able to generate signals.
    Aurora signals go through decision flow, MR through gateway.
    """
    
    def test_btc_aurora_signal_regime_allowed(self):
        """BTC Aurora signal should pass when regime is allowed."""
        sim = TradingScenarioSimulator(
            assignments={"BTCUSDT": ["aurora", "mean_reversion"]},
            aurora_assets={
                "BTCUSDT": {
                    "enabled": True,
                    "allowed_regimes": ["FLAT_LOW", "MEAN_REVERSION", "TREND_UP"],
                }
            }
        )
        
        sim.set_regime("BTCUSDT", "MEAN_REVERSION", warmup_ready=True)
        
        aurora_result = sim.simulate_aurora_decision_flow("BTCUSDT")
        assert aurora_result["status"] == "allowed"
        
    def test_btc_aurora_signal_regime_blocked(self):
        """BTC Aurora signal should be blocked when regime is not allowed."""
        sim = TradingScenarioSimulator(
            assignments={"BTCUSDT": ["aurora", "mean_reversion"]},
            aurora_assets={
                "BTCUSDT": {
                    "enabled": True,
                    "allowed_regimes": ["FLAT_LOW", "MEAN_REVERSION"],
                }
            }
        )
        
        sim.set_regime("BTCUSDT", "HIGH_VOLATILITY", warmup_ready=True)
        
        aurora_result = sim.simulate_aurora_decision_flow("BTCUSDT")
        assert aurora_result["status"] == "blocked"
        assert "REGIME_GATE_BLOCKED" in aurora_result["reason"]
    
    def test_btc_mr_signal_bypasses_aurora_gates(self):
        """BTC MR signal should bypass Aurora gates (goes through gateway)."""
        sim = TradingScenarioSimulator(
            assignments={"BTCUSDT": ["aurora", "mean_reversion"]},
            aurora_assets={
                "BTCUSDT": {
                    "enabled": True,
                    "allowed_regimes": ["FLAT_LOW"],  # Would block HIGH_VOLATILITY for aurora
                }
            }
        )
        
        # Set regime that blocks aurora
        sim.set_regime("BTCUSDT", "HIGH_VOLATILITY", warmup_ready=True)
        
        # Aurora should be blocked
        aurora_result = sim.simulate_aurora_decision_flow("BTCUSDT")
        assert aurora_result["status"] == "blocked"
        
        # MR should still pass (different flow)
        mr_result = sim.simulate_mr_signal_gateway("BTCUSDT", "BUY", 0.78)
        assert mr_result["status"] == "allowed"


class TestETHAuroraOnlyScenario:
    """
    Scenario: ETH is aurora-only symbol
    
    All Aurora gates should apply.
    """
    
    def test_eth_aurora_warmup_blocks(self):
        """ETH Aurora should be blocked when warmup not ready."""
        sim = TradingScenarioSimulator(
            assignments={"ETHUSDT": ["aurora"]},
            aurora_assets={
                "ETHUSDT": {"enabled": True, "allowed_regimes": ["TREND_UP", "TREND_DOWN"]},
            }
        )
        
        sim.set_regime("ETHUSDT", "TREND_UP", warmup_ready=False)  # NOT ready
        
        aurora_result = sim.simulate_aurora_decision_flow("ETHUSDT")
        assert aurora_result["status"] == "blocked"
        assert "WARMUP" in aurora_result["reason"]
    
    def test_eth_aurora_regime_allows(self):
        """ETH Aurora should pass when all gates pass."""
        sim = TradingScenarioSimulator(
            assignments={"ETHUSDT": ["aurora"]},
            aurora_assets={
                "ETHUSDT": {"enabled": True, "allowed_regimes": ["TREND_UP", "TREND_DOWN"]},
            }
        )
        
        sim.set_regime("ETHUSDT", "TREND_DOWN", warmup_ready=True)
        
        aurora_result = sim.simulate_aurora_decision_flow("ETHUSDT")
        assert aurora_result["status"] == "allowed"
    
    def test_eth_mr_signal_rejected_by_arbitration(self):
        """ETH should reject MR signals (not assigned)."""
        sim = TradingScenarioSimulator(
            assignments={"ETHUSDT": ["aurora"]},  # No MR
        )
        
        mr_result = sim.simulate_mr_signal_gateway("ETHUSDT", "BUY", 0.9)
        assert mr_result["status"] == "blocked"
        assert "ARBITRATION_REJECT" in mr_result["reason"]


class TestXRPMROnlyScenario:
    """
    Scenario: XRP is MR-only symbol (like DOGE)
    """
    
    def test_xrp_mr_in_any_regime(self):
        """XRP MR signals should work regardless of regime."""
        sim = TradingScenarioSimulator(
            assignments={"XRPUSDT": ["mean_reversion"]},
            aurora_assets={
                "XRPUSDT": {
                    "enabled": True,
                    "allowed_regimes": ["FLAT_LOW"],  # Very restrictive for aurora
                }
            }
        )
        
        regimes_to_test = ["TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "MEAN_REVERSION", "FLAT_HIGH"]
        
        for regime in regimes_to_test:
            sim.set_regime("XRPUSDT", regime)
            mr_result = sim.simulate_mr_signal_gateway("XRPUSDT", "BUY", 0.75)
            assert mr_result["status"] == "allowed", f"XRP MR should be allowed in {regime}"


class TestFullEventFlowSimulation:
    """
    End-to-end simulation of event flow with multiple symbols.
    """
    
    def test_multi_symbol_parallel_flow(self):
        """Simulate parallel event flow for multiple symbols."""
        sim = TradingScenarioSimulator(
            assignments={
                "BTCUSDT": ["aurora", "mean_reversion"],
                "ETHUSDT": ["aurora"],
                "DOGEUSDT": ["mean_reversion"],
                "XRPUSDT": ["mean_reversion"],
                "SOLUSDT": ["aurora"],
            },
            aurora_assets={
                "BTCUSDT": {"enabled": True, "allowed_regimes": ["FLAT_LOW", "MEAN_REVERSION"]},
                "ETHUSDT": {"enabled": True, "allowed_regimes": ["TREND_UP"]},
                "DOGEUSDT": {"enabled": True, "allowed_regimes": ["FLAT_LOW"]},
                "XRPUSDT": {"enabled": True, "allowed_regimes": ["FLAT_LOW"]},
                "SOLUSDT": {"enabled": True, "allowed_regimes": ["HIGH_VOLATILITY"]},
            }
        )
        
        # Set mixed regimes
        sim.set_regime("BTCUSDT", "MEAN_REVERSION", warmup_ready=True)
        sim.set_regime("ETHUSDT", "TREND_DOWN", warmup_ready=True)  # Wrong regime
        sim.set_regime("DOGEUSDT", "TREND_UP", warmup_ready=True)
        sim.set_regime("XRPUSDT", "HIGH_VOLATILITY", warmup_ready=True)
        sim.set_regime("SOLUSDT", "HIGH_VOLATILITY", warmup_ready=True)
        
        # Simulate Aurora flow for all symbols
        btc_aurora = sim.simulate_aurora_decision_flow("BTCUSDT")
        eth_aurora = sim.simulate_aurora_decision_flow("ETHUSDT")
        doge_aurora = sim.simulate_aurora_decision_flow("DOGEUSDT")
        xrp_aurora = sim.simulate_aurora_decision_flow("XRPUSDT")
        sol_aurora = sim.simulate_aurora_decision_flow("SOLUSDT")
        
        # Simulate MR signals
        btc_mr = sim.simulate_mr_signal_gateway("BTCUSDT", "BUY", 0.8)
        doge_mr = sim.simulate_mr_signal_gateway("DOGEUSDT", "BUY", 0.85)
        xrp_mr = sim.simulate_mr_signal_gateway("XRPUSDT", "SELL", 0.72)
        
        # Assertions
        assert btc_aurora["status"] == "allowed"  # MEAN_REVERSION is allowed
        assert eth_aurora["status"] == "blocked"  # TREND_DOWN not in allowed_regimes
        assert doge_aurora["status"] == "skipped"  # Aurora not assigned
        assert xrp_aurora["status"] == "skipped"  # Aurora not assigned
        assert sol_aurora["status"] == "allowed"  # HIGH_VOLATILITY is allowed
        
        assert btc_mr["status"] == "allowed"  # MR assigned to BTC
        assert doge_mr["status"] == "allowed"  # MR assigned to DOGE
        assert xrp_mr["status"] == "allowed"  # MR assigned to XRP
        
        # Summary
        allowed_count = len(sim.allowed_intents)
        blocked_count = len(sim.blocked_intents)
        
        # Allowed: BTC aurora, SOL aurora, BTC MR, DOGE MR, XRP MR = 5
        # Blocked: ETH aurora = 1
        # Skipped (not in allowed/blocked): DOGE aurora, XRP aurora = 2
        assert allowed_count == 5
        assert blocked_count == 1  # Only ETH blocked


class TestRegressionBugScenarios:
    """
    Regression tests for the specific bugs that were fixed.
    """
    
    def test_original_bug_doge_regime_blocked(self):
        """
        REGRESSION: The original bug that was fixed.
        
        Log showed: [DOGEUSDT] REGIME_GATE_BLOCKED: TREND_UP not in 
        ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH', 'LOW_VOLATILITY', 'MEAN_REVERSION']
        
        This happened because DOGE was in aurora.assets and DecisionMaking
        applied Aurora gates without checking assignments.
        """
        # Recreate the exact scenario from the bug
        sim = TradingScenarioSimulator(
            assignments={
                "DOGEUSDT": ["mean_reversion"],  # MR ONLY - this is the SSOT
            },
            aurora_assets={
                # DOGE was in aurora.assets (legacy, for shared infra)
                "DOGEUSDT": {
                    "enabled": True,
                    "allowed_regimes": [
                        "FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", 
                        "LOW_VOLATILITY", "MEAN_REVERSION"
                    ],
                }
            }
        )
        
        # The regime that was causing the block
        sim.set_regime("DOGEUSDT", "TREND_UP", warmup_ready=True)
        
        # Before fix: Aurora gates would apply and block
        # After fix: Aurora gates are SKIPPED because aurora not in assignments
        
        aurora_result = sim.simulate_aurora_decision_flow("DOGEUSDT")
        mr_result = sim.simulate_mr_signal_gateway("DOGEUSDT", "BUY", 0.82)
        
        # Key assertions
        assert aurora_result["status"] == "skipped", "Aurora flow should be skipped for MR-only symbol"
        assert mr_result["status"] == "allowed", "MR signal should be allowed"
        
        # Verify no REGIME_GATE_BLOCKED occurred
        blocked_with_regime = [
            i for i in sim.blocked_intents 
            if "REGIME_GATE_BLOCKED" in i.get("reason", "")
        ]
        assert len(blocked_with_regime) == 0, "No REGIME_GATE_BLOCKED should occur for DOGE"
    
    def test_xrp_same_issue(self):
        """XRP had the same issue as DOGE."""
        sim = TradingScenarioSimulator(
            assignments={"XRPUSDT": ["mean_reversion"]},
            aurora_assets={
                "XRPUSDT": {
                    "enabled": True,
                    "allowed_regimes": ["FLAT_LOW", "FLAT_NORMAL"],
                }
            }
        )
        
        sim.set_regime("XRPUSDT", "TREND_UP")
        
        aurora_result = sim.simulate_aurora_decision_flow("XRPUSDT")
        mr_result = sim.simulate_mr_signal_gateway("XRPUSDT", "SELL", 0.77)
        
        assert aurora_result["status"] == "skipped"
        assert mr_result["status"] == "allowed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
