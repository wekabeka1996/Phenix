"""
Unit Tests for QuadraticScoringKernel — Aurora Phase 9.
"""

import decimal
import math
import pytest

from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
    QuadraticScoringKernel,
)
from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
    ScoringResult,
    SideBiasState,
)
from apps.reference.domains.decision_making.shields.null_shield import NullShield


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
            pillar_contribs={"tactician": 0.15, "operator": 0.25, "strategist": 0.2},
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
