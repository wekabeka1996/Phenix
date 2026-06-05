"""
Unit Tests for QuadraticScoringKernel — Aurora Phase 9.
"""

import decimal
import math
import pytest

from apps.reference.shared.decision_primitives.scoring_kernel import (
    QuadraticScoringKernel,
)
from apps.reference.shared.decision_primitives.scoring_kernel import (
    ScoringResult,
    SideBiasState,
)
from apps.reference.shared.decision_primitives.shields.null_shield import NullShield


def _base_kwargs(**overrides):
    """Provide sane defaults for QuadraticScoringKernel.compute()."""
    defaults = dict(
        symbol="BTCUSDT",
        features={"pillar_sum": 0.5},
        warmup_readiness={},
        price=decimal.Decimal("50000"),
        signal_weights={},
        feature_neutrals={},
        essential_features=[],
        base_threshold=decimal.Decimal("0.1"),
        regime_name="trending",
        regime_thresholds={"trending": 1.0, "DEFAULT": 1.0},
        side_bias_state=None,
        direction_strength_cfg={},
        delta_price_cap_pct=decimal.Decimal("0.005"),
        neutral_threshold=decimal.Decimal("0.05"),
        current_side="",
    )
    defaults.update(overrides)
    return defaults


class TestQuadraticTransform:
    def test_positive_pillar(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.5}
        ))
        assert float(r.score) == pytest.approx(0.25, abs=1e-6)
        assert r.side == "buy"

    def test_negative_pillar(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": -0.5}
        ))
        assert float(r.score) == pytest.approx(-0.25, abs=1e-6)
        assert r.side == "sell"


class TestPillarSumEdgeCases:
    def test_missing_pillar_sum_defers(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={}
        ))
        assert r.deferred is True
        assert "PILLAR" in r.defer_reason

    def test_none_pillar_sum_defers(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": None}
        ))
        assert r.deferred is True
        assert "PILLAR" in r.defer_reason

    def test_nan_pillar_sum_defers(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": float("nan")}
        ))
        assert r.deferred is True
        assert "NAN_INF" in r.defer_reason


class TestExplainability:
    def test_psi_vector_has_quadratic_fields(self):
        r = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.6},
            pillar_contribs={"tactician": 0.15,
                             "operator": 0.25, "strategist": 0.2},
        ))
        psi = r.psi_vector
        assert psi["scoring_engine"] == "quadratic_v1"
        # The fields are now standardized in Phase 14
        assert "s_linear" in psi
        assert "final_exposure" in psi
        assert psi["final_exposure"] == pytest.approx(0.36, abs=1e-6)
        assert psi["raw_exposure"] == pytest.approx(0.36, abs=1e-6)
        assert psi["final_score"] == pytest.approx(0.36, abs=1e-6)
        assert psi["threshold_factor"] == pytest.approx(1.0, abs=1e-6)
        assert psi["thr_buy"] == pytest.approx(0.1, abs=1e-6)
        assert psi["thr_sell"] == pytest.approx(0.1, abs=1e-6)
        assert psi["buy_bias_mult"] == pytest.approx(1.0, abs=1e-6)
        assert psi["sell_bias_mult"] == pytest.approx(1.0, abs=1e-6)
        assert "side_why" in psi


class TestDeprecatedParamInvariance:
    """PKG-A1: signal_weights and feature_neutrals must not affect kernel output.

    QuadraticScoringKernel reads pillar_sum only. These params are accepted for
    backward-compat call-site compatibility but are silently ignored.
    """

    def test_signal_weights_does_not_affect_score(self):
        base = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.4},
            signal_weights=None,
        ))
        with_weights = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.4},
            signal_weights={"obi": 0.99, "tfi": 0.99, "macro_resid": -0.5},
        ))
        assert float(base.score) == pytest.approx(
            float(with_weights.score), abs=1e-9)
        assert base.side == with_weights.side
        assert float(base.decision_score) == pytest.approx(
            float(with_weights.decision_score), abs=1e-9)

    def test_feature_neutrals_does_not_affect_score(self):
        base = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": -0.3},
            feature_neutrals=None,
        ))
        with_neutrals = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": -0.3},
            feature_neutrals={"obi": 0.5, "ema_bias": 0.9, "tfi": 0.1},
        ))
        assert float(base.score) == pytest.approx(
            float(with_neutrals.score), abs=1e-9)
        assert base.side == with_neutrals.side

    def test_empty_vs_none_signal_weights_identical(self):
        none_result = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.6},
            signal_weights=None,
        ))
        empty_result = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.6},
            signal_weights={},
        ))
        assert float(none_result.score) == pytest.approx(
            float(empty_result.score), abs=1e-9)
        assert none_result.side == empty_result.side

    def test_pillar_sum_is_sole_scoring_input(self):
        r_half = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.5},
            signal_weights={"obi": 9.9},
            feature_neutrals={"obi": 9.9},
        ))
        r_zero = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.0},
            signal_weights={"obi": 9.9},
            feature_neutrals={"obi": 9.9},
        ))
        assert r_zero.deferred is False
        assert float(r_zero.score) == pytest.approx(0.0, abs=1e-9)
        assert float(r_half.score) == pytest.approx(0.25, abs=1e-6)

    def test_admission_mode_linear_decouples_scores(self):
        r_quadratic = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.4},
            admission_mode="quadratic",
            sizing_mode="quadratic",
        ))
        r_linear_admission = QuadraticScoringKernel.compute(**_base_kwargs(
            features={"pillar_sum": 0.4},
            admission_mode="linear",
            sizing_mode="quadratic",
        ))
        # linear admission score != quadratic admission score for same pillar_sum
        assert float(r_quadratic.decision_score) != pytest.approx(
            float(r_linear_admission.decision_score), abs=1e-6)
        # both should agree on side
        assert r_quadratic.side == r_linear_admission.side
