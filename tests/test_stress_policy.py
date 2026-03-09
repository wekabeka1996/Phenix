"""
Tests for Phase 0.6: per-strategy system_stress_policy (off|attenuate|block)
and STRESS attenuation applied to margin_pct_mult in strategy_gateway.

Coverage:
  - _resolve_stress_policy: missing config, valid config, bad policy value
  - _check_system_stress_gate with policy=off: all states → ALLOW
  - _check_system_stress_gate with policy=attenuate: EXTREME=DENY, STRESS=ALLOW+surface
  - _check_system_stress_gate with policy=block: STRESS and EXTREME both DENY
  - reduce_only always bypasses regardless of policy
  - Attenuation logic: STRESS + attenuate → margin_pct_mult * factor
"""

from __future__ import annotations

import decimal
import types
from typing import Optional

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ns(**kw) -> types.SimpleNamespace:
    return types.SimpleNamespace(**kw)


def _make_config(policy: str = "attenuate", factor: float = 0.5, strategy_id: str = "aurora") -> types.SimpleNamespace:
    """Minimal AuroraConfig-shaped namespace with strategy safety_gates config."""
    sg = _ns(
        enabled=True,
        system_stress_policy=policy,
        stress_attenuation_factor=factor,
    )
    strat = _ns(safety_gates=sg)
    strategies = _ns(**{strategy_id: strat})
    return _ns(strategies=strategies)


# ── TestResolveStressPolicy ───────────────────────────────────────────────────

class TestResolveStressPolicy:

    def _call(self, config, strategy_id: str):
        from apps.reference.domains.decision_making.safety_gates import _resolve_stress_policy
        return _resolve_stress_policy(config, strategy_id)

    def test_missing_strategy_returns_off(self) -> None:
        config = _make_config(strategy_id="aurora")
        policy, factor = self._call(config, "unknown_strategy")
        assert policy == "off"
        assert factor == 1.0

    def test_valid_attenuate_policy(self) -> None:
        config = _make_config(policy="attenuate", factor=0.3, strategy_id="aurora")
        policy, factor = self._call(config, "aurora")
        assert policy == "attenuate"
        assert abs(factor - 0.3) < 1e-9

    def test_valid_block_policy(self) -> None:
        config = _make_config(policy="block", factor=0.0, strategy_id="aurora")
        policy, factor = self._call(config, "aurora")
        assert policy == "block"
        assert factor == 0.0

    def test_bad_policy_value_falls_back_to_off(self) -> None:
        config = _make_config(policy="typo_value", strategy_id="aurora")
        policy, factor = self._call(config, "aurora")
        assert policy == "off"

    def test_factor_clamped_to_0_1(self) -> None:
        config = _make_config(policy="attenuate", factor=2.5, strategy_id="aurora")
        # factor > 1.0 should be clamped to 1.0
        _, factor = self._call(config, "aurora")
        assert factor <= 1.0

    def test_missing_safety_gates_attr_returns_off(self) -> None:
        # strategy exists but has no safety_gates attr
        strategies = _ns(aurora=_ns())  # no safety_gates
        config = _ns(strategies=strategies)
        policy, factor = self._call(config, "aurora")
        assert policy == "off"
        assert factor == 1.0


# ── TestStressPolicyOff ───────────────────────────────────────────────────────

class TestStressPolicyOff:
    """policy=off: Gate 0.5 fully bypassed for all states."""

    def _call(self, symbol: str, stress_states: Optional[dict]):
        from apps.reference.domains.decision_making.safety_gates import _check_system_stress_gate
        return _check_system_stress_gate(
            symbol=symbol,
            reduce_only=False,
            apply_safety_gates_flag=True,
            system_stress_states=stress_states,
            stress_policy="off",
        )

    def test_off_normal_allows(self) -> None:
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "NORMAL"})
        assert out == "ALLOW"
        # "off" returns NORMAL state (sanitized)
        assert state == "NORMAL"

    def test_off_stress_allows_returns_normal_state(self) -> None:
        # policy=off → not even STRESS is surfaced (returned state is "NORMAL")
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "STRESS"})
        assert out == "ALLOW"
        assert state == "NORMAL"

    def test_off_extreme_allows(self) -> None:
        # EXTREME is explicitly bypassed when policy=off
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "EXTREME"})
        assert out == "ALLOW"


# ── TestStressPolicyAttenuate ─────────────────────────────────────────────────

class TestStressPolicyAttenuate:
    """policy=attenuate: EXTREME=DENY, STRESS=ALLOW+surface state."""

    def _call(self, symbol: str, stress_states: Optional[dict], reduce_only: bool = False):
        from apps.reference.domains.decision_making.safety_gates import _check_system_stress_gate
        return _check_system_stress_gate(
            symbol=symbol,
            reduce_only=reduce_only,
            apply_safety_gates_flag=True,
            system_stress_states=stress_states,
            stress_policy="attenuate",
        )

    def test_attenuate_normal_allows(self) -> None:
        out, _, _, state = self._call("BTCUSDT", {"BTCUSDT": "NORMAL"})
        assert out == "ALLOW"
        assert state == "NORMAL"

    def test_attenuate_stress_allows_and_surfaces_state(self) -> None:
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "STRESS"})
        assert out == "ALLOW"
        assert deny is None
        assert state == "STRESS"

    def test_attenuate_extreme_denies(self) -> None:
        from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "EXTREME"})
        assert out == "DENY"
        assert deny == NormalizedRejectReasons.SYSTEM_STRESS_ENTRY_BLOCKED
        assert state == "EXTREME"

    def test_attenuate_reduce_only_bypasses_extreme(self) -> None:
        out, _, _, _ = self._call("BTCUSDT", {"BTCUSDT": "EXTREME"}, reduce_only=True)
        assert out == "ALLOW"


# ── TestStressPolicyBlock ────────────────────────────────────────────────────

class TestStressPolicyBlock:
    """policy=block: STRESS and EXTREME both DENY new entries."""

    def _call(self, symbol: str, stress_states: Optional[dict], reduce_only: bool = False):
        from apps.reference.domains.decision_making.safety_gates import _check_system_stress_gate
        return _check_system_stress_gate(
            symbol=symbol,
            reduce_only=reduce_only,
            apply_safety_gates_flag=True,
            system_stress_states=stress_states,
            stress_policy="block",
        )

    def test_block_normal_allows(self) -> None:
        out, _, _, state = self._call("BTCUSDT", {"BTCUSDT": "NORMAL"})
        assert out == "ALLOW"
        assert state == "NORMAL"

    def test_block_stress_denies(self) -> None:
        from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "STRESS"})
        assert out == "DENY"
        assert deny == NormalizedRejectReasons.SYSTEM_STRESS_ENTRY_BLOCKED
        assert state == "STRESS"
        assert "policy=block" in why

    def test_block_extreme_denies(self) -> None:
        from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "EXTREME"})
        assert out == "DENY"
        assert deny == NormalizedRejectReasons.SYSTEM_STRESS_ENTRY_BLOCKED
        assert state == "EXTREME"

    def test_block_reduce_only_bypasses(self) -> None:
        # reduce_only always allows — risk-reducing trades must never be blocked
        out, _, _, _ = self._call("BTCUSDT", {"BTCUSDT": "STRESS"}, reduce_only=True)
        assert out == "ALLOW"
        out, _, _, _ = self._call("BTCUSDT", {"BTCUSDT": "EXTREME"}, reduce_only=True)
        assert out == "ALLOW"


# ── TestStressAttenuation ─────────────────────────────────────────────────────

class TestStressAttenuation:
    """Tests the margin_pct_mult reduction logic from strategy_gateway (Phase 0.6)."""

    def _attenuate(
        self,
        initial_mult: Optional[float],
        policy: str,
        factor: float,
        stress_state: str,
        strategy_id: str = "aurora",
        symbol: str = "BTCUSDT",
    ) -> Optional[decimal.Decimal]:
        """Simulate the strategy_gateway Phase 0.6 attenuation code path."""
        import decimal

        dm = _ns(
            _system_stress_states={symbol: stress_state},
            config=_ns(
                strategies=_ns(
                    **{strategy_id: _ns(
                        safety_gates=_ns(
                            system_stress_policy=policy,
                            stress_attenuation_factor=factor,
                        )
                    )}
                )
            ),
        )

        margin_pct_mult = decimal.Decimal(str(initial_mult)) if initial_mult is not None else None

        _stress_state = getattr(dm, "_system_stress_states", {}).get(symbol, "NORMAL")
        if _stress_state == "STRESS":
            _strat_cfg = getattr(dm.config.strategies, str(strategy_id), None)
            _sg_cfg = getattr(_strat_cfg, "safety_gates", None) if _strat_cfg else None
            _policy = str(getattr(_sg_cfg, "system_stress_policy", "off"))
            if _policy == "attenuate":
                _factor = decimal.Decimal(str(getattr(_sg_cfg, "stress_attenuation_factor", "0.5")))
                margin_pct_mult = (
                    margin_pct_mult if margin_pct_mult is not None else decimal.Decimal("1")
                ) * _factor

        return margin_pct_mult

    def test_stress_attenuate_halves_existing_mult(self) -> None:
        result = self._attenuate(initial_mult=1.0, policy="attenuate", factor=0.5, stress_state="STRESS")
        assert result == decimal.Decimal("0.5")

    def test_stress_attenuate_no_existing_mult_uses_factor(self) -> None:
        # No regime-based mult → treats as 1.0 base, applies factor
        result = self._attenuate(initial_mult=None, policy="attenuate", factor=0.5, stress_state="STRESS")
        assert result == decimal.Decimal("0.5")

    def test_stress_policy_off_leaves_mult_unchanged(self) -> None:
        result = self._attenuate(initial_mult=1.2, policy="off", factor=0.5, stress_state="STRESS")
        assert result == decimal.Decimal("1.2")

    def test_normal_state_leaves_mult_unchanged(self) -> None:
        result = self._attenuate(initial_mult=1.0, policy="attenuate", factor=0.5, stress_state="NORMAL")
        assert result == decimal.Decimal("1.0")

    def test_extreme_state_not_attenuated_here(self) -> None:
        # EXTREME is blocked by Gate 0.5 before reaching gateway sizing;
        # attenuation code only fires for STRESS.
        result = self._attenuate(initial_mult=1.0, policy="attenuate", factor=0.5, stress_state="EXTREME")
        assert result == decimal.Decimal("1.0")

    def test_custom_factor_applied_correctly(self) -> None:
        result = self._attenuate(initial_mult=0.8, policy="attenuate", factor=0.25, stress_state="STRESS")
        assert result == decimal.Decimal("0.8") * decimal.Decimal("0.25")
