"""
S2-1: Integration test — pillar indicators → aggregate → QuadraticKernel.

Verifies end-to-end: raw candle data → compute_* pure functions →
aggregate_pillars → pillar_sum → QuadraticScoringKernel.compute() → non-zero score.
No handler mocking; tests the pure numeric pipeline.
"""
import decimal
import math
import unittest

from apps.reference.domains.feature_engineering.pillar_indicators import (
    aggregate_pillars,
    compute_operator,
    compute_strategist,
    compute_tactician,
)
from apps.reference.shared.decision_primitives.scoring_kernel import (
    QuadraticScoringKernel,
)


def _kernel_kwargs(**overrides):
    """Minimal defaults for QuadraticScoringKernel.compute()."""
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


# ── Synthetic candle data ──────────────────────────────────────────
# Trending up: 200+ bars from 40000 → ~50000 with noise
_N = 210
_M15_CLOSES = [40000 + i * 50 + (i % 7) * 3 for i in range(_N)]
_H4_CLOSES = [40000 + i * 200 + (i % 5) * 10 for i in range(_N)]
_H4_HIGHS = [c + 80 for c in _H4_CLOSES]
_H4_LOWS = [c - 80 for c in _H4_CLOSES]
_D1_CLOSES = [40000 + i * 50 for i in range(_N)]


class TestPillarToKernelE2E(unittest.TestCase):
    """Pure numeric pipeline: pillars → aggregate → quadratic kernel."""

    def test_pillars_compute_non_none(self):
        """All three pillars return valid floats on sufficient candle data."""
        t = compute_tactician(_M15_CLOSES)
        o = compute_operator(_H4_CLOSES, _H4_HIGHS, _H4_LOWS)
        s = compute_strategist(_D1_CLOSES)
        for name, val in [("tactician", t), ("operator", o), ("strategist", s)]:
            self.assertIsNotNone(val, f"{name} is None on {_N} bars")
            self.assertTrue(math.isfinite(val), f"{name} is not finite: {val}")
            self.assertGreaterEqual(val, -1.0, f"{name} < -1")
            self.assertLessEqual(val, 1.0, f"{name} > 1")

    def test_aggregate_weighted_sum(self):
        """aggregate_pillars returns weighted sum in [-1, +1]."""
        t = compute_tactician(_M15_CLOSES)
        o = compute_operator(_H4_CLOSES, _H4_HIGHS, _H4_LOWS)
        s = compute_strategist(_D1_CLOSES)
        weights = {"tactician": 0.30, "operator": 0.40, "strategist": 0.30}
        ps = aggregate_pillars(t, o, s, weights)
        self.assertIsNotNone(ps)
        self.assertTrue(-1.0 <= ps <= 1.0, f"pillar_sum={ps} out of [-1,1]")

    def test_kernel_produces_nonzero_score(self):
        """QuadraticKernel with valid pillar_sum → non-zero score + correct sign."""
        t = compute_tactician(_M15_CLOSES)
        o = compute_operator(_H4_CLOSES, _H4_HIGHS, _H4_LOWS)
        s = compute_strategist(_D1_CLOSES)
        weights = {"tactician": 0.30, "operator": 0.40, "strategist": 0.30}
        ps = aggregate_pillars(t, o, s, weights)
        self.assertIsNotNone(ps)

        result = QuadraticScoringKernel.compute(
            **_kernel_kwargs(
                features={"pillar_sum": ps},
                pillar_contribs={
                    "tactician": t * 0.3,
                    "operator": o * 0.4,
                    "strategist": s * 0.3,
                },
            )
        )
        score_f = float(result.score)
        self.assertNotEqual(score_f, 0.0, "Score should be non-zero for valid pillar_sum")
        # Quadratic: sign(Σ)×Σ² — sign must match pillar_sum
        if ps > 0:
            self.assertGreater(score_f, 0.0)
        else:
            self.assertLess(score_f, 0.0)

    def test_kernel_quadratic_transform(self):
        """Kernel score ≈ sign(Σ) × Σ² (no shield attenuation)."""
        ps = 0.6
        result = QuadraticScoringKernel.compute(
            **_kernel_kwargs(features={"pillar_sum": ps})
        )
        expected = ps ** 2  # sign(0.6)=+1, 0.6²=0.36
        self.assertAlmostEqual(float(result.score), expected, places=2)

    def test_kernel_defers_on_missing_pillar_sum(self):
        """Kernel with missing pillar_sum → deferred (fail-closed)."""
        result = QuadraticScoringKernel.compute(
            **_kernel_kwargs(features={})  # no pillar_sum
        )
        self.assertTrue(result.deferred, "Should defer on missing pillar_sum")
        self.assertIn("PILLAR_WARMUP", result.defer_reason or "")

    def test_kernel_defers_on_nan_pillar_sum(self):
        """Kernel with NaN pillar_sum → deferred (fail-closed)."""
        result = QuadraticScoringKernel.compute(
            **_kernel_kwargs(features={"pillar_sum": float("nan")})
        )
        self.assertTrue(result.deferred, "Should defer on NaN pillar_sum")

    def test_psi_vector_populated(self):
        """PSI vector contains scoring engine identifier and s_linear."""
        ps = 0.5
        result = QuadraticScoringKernel.compute(
            **_kernel_kwargs(features={"pillar_sum": ps})
        )
        psi = result.psi_vector or {}
        self.assertEqual(psi.get("scoring_engine"), "quadratic_v1")
        self.assertAlmostEqual(float(psi.get("s_linear", 0)), ps)


if __name__ == "__main__":
    unittest.main()
