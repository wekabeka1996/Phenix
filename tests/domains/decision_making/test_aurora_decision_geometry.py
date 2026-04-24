from __future__ import annotations

import decimal

import pytest

from apps.reference.config_models import DecisionGeometryConfig
from apps.reference.shared.decision_primitives.scoring_kernel import (
    QuadraticScoringKernel,
)


def _compute(*, pillar_sum: float, shield_mult: float, threshold: str = "0.02", **kwargs):
    return QuadraticScoringKernel.compute(
        symbol="ETHUSDT",
        features={"pillar_sum": pillar_sum},
        warmup_readiness={},
        price=decimal.Decimal("100"),
        signal_weights={},
        feature_neutrals={},
        essential_features=[],
        base_threshold=decimal.Decimal(threshold),
        regime_name="DEFAULT",
        regime_thresholds={"DEFAULT": 1.0},
        side_bias_state=None,
        direction_strength_cfg={},
        delta_price_cap_pct=decimal.Decimal("0.02"),
        neutral_threshold=decimal.Decimal("0.01"),
        current_side="",
        shield_fn=lambda *_args: (shield_mult, ["TEST_SHIELD"]),
        score_multiplier=1.0,
        **kwargs,
    )


def test_quadratic_baseline_preserves_coupled_score() -> None:
    result = _compute(pillar_sum=0.4, shield_mult=0.6)

    assert result.score == decimal.Decimal("0.096")
    assert result.decision_score == decimal.Decimal("0.096")
    assert result.sizing_score == decimal.Decimal("0.096")
    assert result.admission_shield_multiplier == decimal.Decimal("0.6")
    assert result.side == "buy"


def test_linear_admission_quadratic_sizing_decouples_scores() -> None:
    result = _compute(
        pillar_sum=0.04,
        shield_mult=0.6,
        admission_mode="linear",
        sizing_mode="quadratic",
        admission_shield_floor=0.75,
    )

    assert result.raw_score == decimal.Decimal("0.04")
    assert result.decision_score == decimal.Decimal("0.03")
    assert result.sizing_score == decimal.Decimal("0.00096")
    assert result.score == result.decision_score
    assert result.admission_shield_multiplier == decimal.Decimal("0.75")
    assert result.side == "buy"


def test_admission_shield_floor_does_not_override_hard_veto() -> None:
    result = _compute(
        pillar_sum=0.25,
        shield_mult=0.0,
        admission_mode="linear",
        sizing_mode="quadratic",
        admission_shield_floor=0.75,
    )

    assert result.decision_score == decimal.Decimal("0")
    assert result.sizing_score == decimal.Decimal("0")
    assert result.admission_shield_multiplier == decimal.Decimal("0")
    assert result.side == ""


def test_decision_geometry_requires_soft_power_exponent() -> None:
    with pytest.raises(ValueError):
        DecisionGeometryConfig(
            admission_mode="soft_power", sizing_mode="quadratic")


def test_decision_geometry_rejects_power_for_non_soft_mode() -> None:
    with pytest.raises(ValueError):
        DecisionGeometryConfig(admission_mode="linear", admission_power=1.3)
