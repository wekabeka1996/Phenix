"""Tests for aurora_math.py — Package 2 math layer.

Tests pure numeric transforms in isolation: no policy, no side decisions.
"""
from __future__ import annotations

import math
import pytest

from apps.reference.shared.decision_primitives.aurora_math import (
    AuroraMathInput,
    AuroraMathOutput,
    compute_aurora_math,
    transform_signed_score,
    scale_and_clamp,
    apply_shield_attenuation,
)


# ── transform_signed_score ──────────────────────────────────────────


class TestTransformSignedScore:
    def test_quadratic_positive(self):
        assert transform_signed_score(
            0.5, mode="quadratic", power=None) == pytest.approx(0.25)

    def test_quadratic_negative(self):
        assert transform_signed_score(-0.4, mode="quadratic",
                                      power=None) == pytest.approx(-0.16)

    def test_quadratic_zero(self):
        assert transform_signed_score(0.0, mode="quadratic", power=None) == 0.0

    def test_quadratic_one(self):
        assert transform_signed_score(1.0, mode="quadratic", power=None) == 1.0

    def test_quadratic_minus_one(self):
        assert transform_signed_score(-1.0,
                                      mode="quadratic", power=None) == -1.0

    def test_linear_passthrough(self):
        assert transform_signed_score(0.73, mode="linear", power=None) == 0.73

    def test_linear_negative(self):
        assert transform_signed_score(-0.2, mode="linear", power=None) == -0.2

    def test_soft_power(self):
        result = transform_signed_score(0.5, mode="soft_power", power=1.5)
        expected = 0.5 ** 1.5
        assert result == pytest.approx(expected)

    def test_soft_power_negative(self):
        result = transform_signed_score(-0.5, mode="soft_power", power=1.5)
        expected = -(0.5 ** 1.5)
        assert result == pytest.approx(expected)

    def test_soft_power_requires_exponent(self):
        with pytest.raises(ValueError, match="soft_power"):
            transform_signed_score(0.5, mode="soft_power", power=None)

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="unsupported"):
            transform_signed_score(0.5, mode="cubic", power=None)

    def test_sign_preservation_positive(self):
        """Positive input → positive output for all modes."""
        for mode in ("quadratic", "linear"):
            result = transform_signed_score(0.3, mode=mode, power=None)
            assert result >= 0, f"mode={mode} broke sign preservation"

    def test_sign_preservation_negative(self):
        """Negative input → negative output for all modes."""
        for mode in ("quadratic", "linear"):
            result = transform_signed_score(-0.3, mode=mode, power=None)
            assert result <= 0, f"mode={mode} broke sign preservation"


# ── scale_and_clamp ─────────────────────────────────────────────────


class TestScaleAndClamp:
    def test_no_clamp(self):
        scaled, clamped, was_clamped = scale_and_clamp(0.5, 1.0)
        assert scaled == 0.5
        assert clamped == 0.5
        assert was_clamped is False

    def test_clamp_high(self):
        scaled, clamped, was_clamped = scale_and_clamp(0.6, 2.0)
        assert scaled == 1.2
        assert clamped == 1.0
        assert was_clamped is True

    def test_clamp_low(self):
        scaled, clamped, was_clamped = scale_and_clamp(-0.6, 2.0)
        assert scaled == -1.2
        assert clamped == -1.0
        assert was_clamped is True

    def test_multiplier_zero(self):
        scaled, clamped, _ = scale_and_clamp(0.5, 0.0)
        assert scaled == 0.0
        assert clamped == 0.0


# ── apply_shield_attenuation ────────────────────────────────────────


class TestShieldAttenuation:
    def test_no_attenuation(self):
        ds, ss, asm = apply_shield_attenuation(
            admission_pre_shield=0.16,
            sizing_pre_shield=0.16,
            shield_multiplier=1.0,
            admission_shield_floor=0.0,
        )
        assert ds == pytest.approx(0.16)
        assert ss == pytest.approx(0.16)
        assert asm == pytest.approx(1.0)

    def test_partial_attenuation(self):
        ds, ss, asm = apply_shield_attenuation(
            admission_pre_shield=0.16,
            sizing_pre_shield=0.16,
            shield_multiplier=0.5,
            admission_shield_floor=0.0,
        )
        assert ds == pytest.approx(0.08)
        assert ss == pytest.approx(0.08)
        assert asm == pytest.approx(0.5)

    def test_hard_veto(self):
        ds, ss, asm = apply_shield_attenuation(
            admission_pre_shield=0.16,
            sizing_pre_shield=0.16,
            shield_multiplier=0.0,
            admission_shield_floor=0.75,
        )
        assert ds == 0.0
        assert ss == 0.0
        assert asm == 0.0  # Floor does NOT override hard veto

    def test_admission_shield_floor_lifts(self):
        ds, ss, asm = apply_shield_attenuation(
            admission_pre_shield=0.16,
            sizing_pre_shield=0.16,
            shield_multiplier=0.3,
            admission_shield_floor=0.75,
        )
        assert asm == pytest.approx(0.75)  # Floor lifts from 0.3
        assert ds == pytest.approx(0.16 * 0.75)
        assert ss == pytest.approx(0.16 * 0.3)  # Sizing uses raw shield


# ── compute_aurora_math (integration) ───────────────────────────────


class TestComputeAuroraMath:
    def _make_input(self, s_linear=0.4, **kwargs):
        defaults = dict(
            s_linear=s_linear,
            source="test",
            score_multiplier=1.0,
            admission_mode="quadratic",
            admission_power=None,
            sizing_mode="quadratic",
            sizing_power=None,
            admission_shield_floor=0.0,
            symbol="ETHUSDT",
            features={"pillar_sum": s_linear},
            pillar_contribs={"tactician": 0.2, "operator": 0.2},
        )
        defaults.update(kwargs)
        return AuroraMathInput(**defaults)

    def test_basic_quadratic(self):
        out = compute_aurora_math(self._make_input(0.4))
        assert out.s_linear == 0.4
        assert out.s_clamped == 0.4
        assert out.admission_pre_shield == pytest.approx(0.16)
        assert out.decision_score == pytest.approx(0.16)
        assert out.shield_multiplier == 1.0

    def test_with_shield(self):
        shield = lambda *_: (0.6, ["TEST_SHIELD"])
        out = compute_aurora_math(self._make_input(0.4), shield_fn=shield)
        assert out.shield_multiplier == pytest.approx(0.6)
        assert out.decision_score == pytest.approx(0.16 * 0.6)
        assert out.sizing_score == pytest.approx(0.16 * 0.6)

    def test_clamping(self):
        out = compute_aurora_math(self._make_input(0.6, score_multiplier=2.0))
        assert out.s_scaled_raw == 1.2
        assert out.s_clamped == 1.0
        assert out.clamped is True

    def test_linear_admission(self):
        out = compute_aurora_math(self._make_input(
            0.5, admission_mode="linear", sizing_mode="quadratic"
        ))
        assert out.admission_pre_shield == pytest.approx(0.5)
        assert out.sizing_pre_shield == pytest.approx(0.25)

    def test_output_is_frozen(self):
        out = compute_aurora_math(self._make_input(0.4))
        with pytest.raises(AttributeError):
            out.s_linear = 999

    def test_no_side_decision_in_output(self):
        """Math output must NOT contain side, threshold, or policy fields."""
        out = compute_aurora_math(self._make_input(0.4))
        assert not hasattr(out, "side")
        assert not hasattr(out, "thr_buy")
        assert not hasattr(out, "thr_sell")
        assert not hasattr(out, "threshold_factor")

    def test_negative_input_sign_preserved(self):
        out = compute_aurora_math(self._make_input(-0.3))
        assert out.decision_score < 0
        assert out.sizing_score < 0
