"""
test_llm_safety_gates_contract.py

Tests specifically targeting how apply_safety_gates() behaves for
'llm_microstructure' synthetic signals.

AUDIT FINDING: safety_gates.enabled=true causes deterministic DENY
for LLM signals because:
  1. regime_confidence=None < min_regime_confidence=0.42 (Gate 1)
  2. pm_norm_300s=None, require_bleed_ready=true (Gate 3) — secondary
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Minimal stubs for config + clock
# ---------------------------------------------------------------------------

def _make_clock(now_ms: int = 1_700_000_000_000) -> MagicMock:
    clock = MagicMock()
    clock.now_ms.return_value = now_ms
    return clock


def _make_config(
    safety_gates_enabled: bool = True,
    min_regime_confidence: float = 0.42,
    ds_enabled: bool = True,
    pm_enabled: bool = True,
    require_bleed_ready: bool = True,
    system_stress_policy: str = "off",
) -> MagicMock:
    """Build minimal AuroraConfig mock for llm_microstructure safety gate tests."""
    cfg = MagicMock()

    # llm_microstructure strategy config
    sg_cfg = MagicMock()
    sg_cfg.enabled = safety_gates_enabled
    sg_cfg.system_stress_policy = system_stress_policy
    sg_cfg.stress_attenuation_factor = 0.5
    llm_strat = MagicMock()
    llm_strat.safety_gates = sg_cfg
    cfg.strategies.llm_microstructure = llm_strat

    # directional_sanity config
    ds = MagicMock()
    ds.enabled = ds_enabled
    ds.min_abs_delta_price = 0.0
    ds.min_confidence = 0.0
    ds.min_regime_confidence = min_regime_confidence
    ds.consecutive_bars = 1
    cfg.domains.decision_making.directional_sanity = ds

    # price_motion_sanity config
    pm = MagicMock()
    pm.enabled = pm_enabled
    pm.flash_window_sec = 60
    pm.bleed_window_sec = 300
    pm.flash_threshold_norm = 1.0
    pm.bleed_threshold_norm = 0.5
    pm.require_bleed_ready = require_bleed_ready
    cfg.domains.decision_making.price_motion_sanity = pm
    cfg.trading_mode = "live"

    return cfg


# ---------------------------------------------------------------------------
# H2-A: Gate 1 — regime_confidence=None → DENY (PRIMARY BREAK POINT)
# ---------------------------------------------------------------------------

class TestGate1RegimeConfidenceDeny:
    """
    Proves AUDIT FINDING H2: safety_gates.enabled=true + min_regime_confidence=0.42
    causes deterministic DENY when per_symbol_regimes has no entry for the symbol.

    This is the FIRST PROVEN BREAK POINT for the LLM intent path.
    """

    def test_regime_confidence_none_causes_deny(self):
        from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates

        config = _make_config(
            safety_gates_enabled=True,
            min_regime_confidence=0.42,
        )
        clock = _make_clock()

        # per_symbol_regimes has no entry for the symbol — LLM-only symbol
        per_symbol_regimes: dict = {}
        symbol_states: dict = {}
        system_stress_states: dict = {}

        result = apply_safety_gates(
            symbol="1000PEPEUSDT",
            side="BUY",
            reduce_only=False,
            strategy_id="llm_microstructure",
            decision_ts_ms=clock.now_ms(),
            why_chain=["llm_external_intent", "source:external_llm"],
            config=config,
            clock=clock,
            symbol_states=symbol_states,
            per_symbol_regimes=per_symbol_regimes,
            system_stress_states=system_stress_states,
        )

        assert result.outcome == "DENY", (
            f"Expected DENY but got {result.outcome!r} (deny_reason={result.deny_reason!r}). "
            "PRIMARY BREAK POINT: regime_confidence=None < min=0.42 must block LLM signal."
        )
        assert result.deny_reason is not None
        assert result.regime_confidence is None, (
            "Expected regime_confidence=None for LLM-only symbol (no per_symbol_regimes entry)"
        )

    def test_regime_confidence_below_threshold_causes_deny(self):
        from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates

        config = _make_config(
            safety_gates_enabled=True,
            min_regime_confidence=0.42,
        )
        clock = _make_clock()

        # Regime exists but confidence is below threshold
        per_symbol_regimes = {"1000PEPEUSDT": {"regime": "TREND_UP", "confidence": 0.30}}
        symbol_states: dict = {}

        result = apply_safety_gates(
            symbol="1000PEPEUSDT",
            side="BUY",
            reduce_only=False,
            strategy_id="llm_microstructure",
            decision_ts_ms=clock.now_ms(),
            why_chain=["llm_external_intent"],
            config=config,
            clock=clock,
            symbol_states=symbol_states,
            per_symbol_regimes=per_symbol_regimes,
            system_stress_states={},
        )

        assert result.outcome == "DENY", (
            f"Expected DENY for regime_confidence=0.30 < 0.42 but got {result.outcome!r}"
        )

    def test_safety_gates_disabled_allows_signal(self):
        """
        Proves AUDIT FINDING: setting safety_gates.enabled=false bypasses Gate 1
        and allows synthetic LLM signals through — the minimal safe fix.
        """
        from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates

        config = _make_config(
            safety_gates_enabled=False,  # <-- the fix
            min_regime_confidence=0.42,
        )
        clock = _make_clock()

        # No regime data for LLM-only symbol
        per_symbol_regimes: dict = {}
        symbol_states: dict = {}

        result = apply_safety_gates(
            symbol="1000PEPEUSDT",
            side="BUY",
            reduce_only=False,
            strategy_id="llm_microstructure",
            decision_ts_ms=clock.now_ms(),
            why_chain=["llm_external_intent"],
            config=config,
            clock=clock,
            symbol_states=symbol_states,
            per_symbol_regimes=per_symbol_regimes,
            system_stress_states={},
        )

        assert result.outcome == "ALLOW", (
            f"Expected ALLOW when safety_gates.enabled=False but got {result.outcome!r}. "
            "Fix: set safety_gates.enabled: false in llm_microstructure.yaml"
        )
        assert result.apply_safety_gates is False


# ---------------------------------------------------------------------------
# H2-B: Gate 3 — pm_norm_300s=None, require_bleed_ready=true → DENY (secondary)
# ---------------------------------------------------------------------------

class TestGate3PriceMotionDeny:
    """
    Proves AUDIT FINDING: even if Gate 1 were bypassed (e.g., regime_confidence >= 0.42),
    Gate 3 (price motion) would block the signal because pm_norm_300s=None
    for LLM-only symbols that are not in the aurora feature pipeline.
    """

    def test_pm_none_require_bleed_ready_causes_deny(self):
        from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates

        config = _make_config(
            safety_gates_enabled=True,
            min_regime_confidence=0.0,  # disable Gate 1 to reach Gate 3
            pm_enabled=True,
            require_bleed_ready=True,
        )
        clock = _make_clock()

        # Provide sufficient regime confidence to pass Gate 1
        per_symbol_regimes = {"1000PEPEUSDT": {"regime": "TREND_UP", "confidence": 0.90}}

        # symbol_states has no price_motion data — LLM-only symbol
        symbol_states: dict = {}

        result = apply_safety_gates(
            symbol="1000PEPEUSDT",
            side="BUY",
            reduce_only=False,
            strategy_id="llm_microstructure",
            decision_ts_ms=clock.now_ms(),
            why_chain=["llm_external_intent"],
            config=config,
            clock=clock,
            symbol_states=symbol_states,
            per_symbol_regimes=per_symbol_regimes,
            system_stress_states={},
        )

        # pm_norm_300s=None, require_bleed_ready=True → bleed insufficient → DENY
        assert result.outcome == "DENY", (
            f"Expected DENY from Gate 3 (price_motion bleed) but got {result.outcome!r}. "
            "SECONDARY BLOCKER: pm_norm_300s=None blocks LLM signals even after Gate 1 fix."
        )
        assert result.pm_norm_300s is None

    def test_pm_gate_disabled_allows(self):
        """Confirms that disabling safety_gates entirely bypasses all gates including Gate 3."""
        from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates

        config = _make_config(
            safety_gates_enabled=False,
            pm_enabled=True,
            require_bleed_ready=True,
        )
        clock = _make_clock()
        per_symbol_regimes = {"1000PEPEUSDT": {"regime": "TREND_UP", "confidence": 0.90}}
        symbol_states: dict = {}

        result = apply_safety_gates(
            symbol="1000PEPEUSDT",
            side="BUY",
            reduce_only=False,
            strategy_id="llm_microstructure",
            decision_ts_ms=clock.now_ms(),
            why_chain=["llm_external_intent"],
            config=config,
            clock=clock,
            symbol_states=symbol_states,
            per_symbol_regimes=per_symbol_regimes,
            system_stress_states={},
        )

        assert result.outcome == "ALLOW", (
            f"Expected ALLOW with safety_gates disabled but got {result.outcome!r}"
        )


# ---------------------------------------------------------------------------
# Deterministic DENY proof: shows ALL gate outcomes for default LLM config
# ---------------------------------------------------------------------------

class TestLLMSafetyGateSummary:
    """
    Comprehensive proof-of-break table for the LLM path.
    """

    def test_default_config_blocks_llm_signal(self):
        """
        With default production config (safety_gates.enabled=true, min_regime_confidence=0.42),
        a synthetic LLM signal for an LLM-only symbol is DENIED at Gate 1.
        This is the root cause identified in the forensic audit.
        """
        from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates

        config = _make_config(
            safety_gates_enabled=True,
            min_regime_confidence=0.42,
        )
        result = apply_safety_gates(
            symbol="1000PEPEUSDT",
            side="BUY",
            reduce_only=False,
            strategy_id="llm_microstructure",
            decision_ts_ms=_make_clock().now_ms(),
            why_chain=["llm_external_intent", "source:external_llm"],
            config=config,
            clock=_make_clock(),
            symbol_states={},
            per_symbol_regimes={},
            system_stress_states={},
        )

        # === PROVEN BREAK POINT ===
        assert result.outcome == "DENY"
        assert result.apply_safety_gates is True
        assert result.regime_confidence is None
        print(
            f"\nAUDIT CONFIRMED: LLM signal DENIED at Gate 1.\n"
            f"  outcome={result.outcome!r}\n"
            f"  deny_reason={result.deny_reason!r}\n"
            f"  why_short={result.why_short!r}\n"
            f"  regime_confidence={result.regime_confidence!r}\n"
            f"  apply_safety_gates={result.apply_safety_gates!r}"
        )
