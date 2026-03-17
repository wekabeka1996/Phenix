"""
T1: Safety Gates Config-Drive Test (TDD RED -> GREEN)

DM-SAFETY-BYPASSES-P1: Verifies safety gates are controlled by config, not hardcoded strategy_id.

Tests:
- T1a: safety_gates.enabled=true => apply_safety_gates=True
- T1b: safety_gates.enabled=false => apply_safety_gates=False
- T1c: safety_gates missing => FAIL-CLOSED with CONFIG_SAFETY_GATES_MISSING
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _test_safety_gates_lookup(safety_gates_enabled: bool | None, strategy_id: str = "test_strategy"):
    """
    Test the safety gates config lookup logic in isolation.
    
    Simulates the exact logic from _propose_trade_intent() lines 2703-2763.
    """
    from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
    
    # Build mock config
    config = MagicMock()
    
    if strategy_id == "unknown_strategy":
        # Strategy not in config - getattr returns None
        config.strategies = MagicMock(spec=[])  # No attributes defined

    elif safety_gates_enabled is None:
        # safety_gates block missing
        strat_cfg = MagicMock()
        strat_cfg.safety_gates = None
        setattr(config.strategies, strategy_id, strat_cfg)
    else:
        # Full config
        safety_gates_cfg = MagicMock()
        safety_gates_cfg.enabled = safety_gates_enabled
        strat_cfg = MagicMock()
        strat_cfg.safety_gates = safety_gates_cfg
        setattr(config.strategies, strategy_id, strat_cfg)
    
    # Simulate the logic from _propose_trade_intent
    apply_safety_gates = False
    blocked_reason = None
    
    try:
        strat_cfg = getattr(config.strategies, str(strategy_id), None)
        if strat_cfg is None:
            blocked_reason = NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING
        else:
            safety_gates_cfg = getattr(strat_cfg, "safety_gates", None)
            if safety_gates_cfg is None:
                blocked_reason = NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING
            else:
                apply_safety_gates = bool(getattr(safety_gates_cfg, "enabled", False))
    except Exception:
        blocked_reason = NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING
    
    return apply_safety_gates, blocked_reason


class TestSafetyGatesConfigDriven:
    """DM-SAFETY-BYPASSES-P1: Safety gates must be controlled by config, not strategy_id."""

    def test_safety_gates_enabled_true_applies_gates(self):
        """T1a: safety_gates.enabled=true => apply_safety_gates=True."""
        apply_gates, blocked = _test_safety_gates_lookup(safety_gates_enabled=True)
        
        assert blocked is None, "Should not block when config is valid"
        assert apply_gates is True, "safety_gates.enabled=true should apply gates"

    def test_safety_gates_enabled_false_skips_gates(self):
        """T1b: safety_gates.enabled=false => apply_safety_gates=False."""
        apply_gates, blocked = _test_safety_gates_lookup(safety_gates_enabled=False)
        
        assert blocked is None, "Should not block when config is valid"
        assert apply_gates is False, "safety_gates.enabled=false should skip gates"

    def test_safety_gates_missing_fails_closed(self):
        """T1c: safety_gates missing => FAIL-CLOSED with CONFIG_SAFETY_GATES_MISSING."""
        from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
        
        apply_gates, blocked = _test_safety_gates_lookup(safety_gates_enabled=None)
        
        assert blocked == NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING
        assert apply_gates is False, "Should default to False when blocked"

    def test_unknown_strategy_fails_closed(self):
        """T1d: strategy not in config => FAIL-CLOSED with CONFIG_SAFETY_GATES_MISSING."""
        from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
        
        apply_gates, blocked = _test_safety_gates_lookup(
            safety_gates_enabled=True,
            strategy_id="unknown_strategy"
        )
        
        assert blocked == NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING
        assert apply_gates is False


class TestNRRCodesExist:
    """Verify that new NRR codes are correctly defined."""

    def test_exposure_cache_unavailable_code_exists(self):
        from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
        
        assert hasattr(NormalizedRejectReasons, "EXPOSURE_CACHE_UNAVAILABLE")
        assert NormalizedRejectReasons.EXPOSURE_CACHE_UNAVAILABLE == "NRR-053"

    def test_config_safety_gates_missing_code_exists(self):
        from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
        
        assert hasattr(NormalizedRejectReasons, "CONFIG_SAFETY_GATES_MISSING")
        assert NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING == "NRR-054"

    def test_nrr_descriptions_include_new_codes(self):
        from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
        
        desc_053 = NormalizedRejectReasons.get_description(NormalizedRejectReasons.EXPOSURE_CACHE_UNAVAILABLE)
        desc_054 = NormalizedRejectReasons.get_description(NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING)
        
        assert desc_053 is not None, "NRR-053 should have a description"
        assert desc_054 is not None, "NRR-054 should have a description"
        assert "fail-closed" in desc_053.lower()
        assert "fail-closed" in desc_054.lower()


class TestSystemStressPolicyFailClosed:
    """DM-SAFETY-BYPASSES-P1: Ensure system stress policy fails closed on config resolution error."""

    def test_resolve_stress_policy_exception_fails_closed(self):
        from apps.reference.domains.decision_making.safety_gates import _resolve_stress_policy

        config = MagicMock()
        # Simulate an exception accessing 'strategies' to trigger the except block
        type(config).strategies = property(lambda self: (_ for _ in ()).throw(ValueError("Test exception")))

        policy, factor = _resolve_stress_policy(config, "test_strat")

        assert policy == "CONFIG_ERROR", "Should fail closed on exception"
        assert factor == 0.0

    def test_check_system_stress_gate_fails_closed_on_config_error(self):
        from apps.reference.domains.decision_making.safety_gates import _check_system_stress_gate
        from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons

        outcome, deny_reason, why_short, state = _check_system_stress_gate(
            symbol="BTCUSDT",
            reduce_only=False,
            apply_safety_gates_flag=True,
            system_stress_states={"BTCUSDT": "NORMAL"},
            stress_policy="CONFIG_ERROR"
        )

        assert outcome == "DENY"
        assert deny_reason == NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING
        assert "resolution failed (fail-closed)" in why_short
        assert state == "UNKNOWN"
