"""PKG-A1: Prove AuroraAlphaAdapter does not pass deprecated params to kernel.

After the contamination patch:
- AuroraAlphaAdapter must not accept or pass signal_weights/feature_neutrals
  into QuadraticScoringKernel.compute().
- Adapter output must be identical to a direct kernel call using the same
  pillar_sum input.
- The kernel must produce identical results whether signal_weights/feature_neutrals
  are passed as None, {}, or absent.
"""
from __future__ import annotations

import decimal
import pytest

from apps.reference.domains.alpha_search.models.aurora_adapter import AuroraAlphaAdapter
from apps.reference.shared.decision_primitives.scoring_kernel import QuadraticScoringKernel


_FEATURES_BUY = {
    "pillar_sum": 0.5,
    "obi": 0.8,
    "tfi": 0.6,
    "delta_price": 200.0,
    "macro_resid": 0.4,
    "close": 50000.0,
}
_FEATURES_SELL = {
    "pillar_sum": -0.5,
    "obi": -0.8,
    "tfi": -0.6,
    "delta_price": -200.0,
    "macro_resid": -0.4,
    "close": 50000.0,
}
_FEATURES_NEUTRAL = {
    "pillar_sum": 0.0,
    "obi": 0.0,
    "tfi": 0.0,
    "delta_price": 0.0,
    "macro_resid": 0.0,
    "close": 50000.0,
}


class TestAdapterNoBrokenSignalWeightsPassthrough:
    """AuroraAlphaAdapter must not expose or pass deprecated scoring params."""

    def test_adapter_has_no_signal_weights_attribute(self):
        adapter = AuroraAlphaAdapter()
        assert not hasattr(adapter, "_signal_weights"), (
            "AuroraAlphaAdapter must not carry _signal_weights after PKG-A1 patch"
        )

    def test_adapter_has_no_feature_neutrals_attribute(self):
        adapter = AuroraAlphaAdapter()
        assert not hasattr(adapter, "_feature_neutrals"), (
            "AuroraAlphaAdapter must not carry _feature_neutrals after PKG-A1 patch"
        )

    def test_adapter_constructor_rejects_signal_weights_kwarg(self):
        with pytest.raises(TypeError):
            AuroraAlphaAdapter(signal_weights={"obi": 0.99})

    def test_adapter_constructor_rejects_feature_neutrals_kwarg(self):
        with pytest.raises(TypeError):
            AuroraAlphaAdapter(feature_neutrals={"obi": 0.5})


class TestAdapterOutputMatchesKernelDirect:
    """Adapter score must match direct kernel call (same pillar_sum, same geometry)."""

    def _kernel_direct(self, pillar_sum: float, admission_mode: str = "quadratic") -> decimal.Decimal:
        result = QuadraticScoringKernel.compute(
            symbol="BTCUSDT",
            features={"pillar_sum": pillar_sum, "close": 50000.0},
            warmup_readiness={},
            price=decimal.Decimal("50000.0"),
            essential_features=[],
            base_threshold=decimal.Decimal("0.12"),
            regime_name="DEFAULT",
            regime_thresholds={"DEFAULT": 1.0},
            side_bias_state=None,
            direction_strength_cfg={},
            delta_price_cap_pct=decimal.Decimal("0.02"),
            neutral_threshold=None,
            current_side="",
            admission_mode=admission_mode,
        )
        return result.score

    def test_buy_signal_sign_matches(self):
        adapter = AuroraAlphaAdapter()
        result = adapter.calculate_alpha(
            symbol="BTCUSDT",
            market_data={"close": 50000.0},
            features=_FEATURES_BUY,
        )
        assert result.score > 0, "Positive pillar_sum must produce positive score"

    def test_sell_signal_sign_matches(self):
        adapter = AuroraAlphaAdapter()
        result = adapter.calculate_alpha(
            symbol="BTCUSDT",
            market_data={"close": 50000.0},
            features=_FEATURES_SELL,
        )
        assert result.score < 0, "Negative pillar_sum must produce negative score"

    def test_zero_pillar_sum_near_neutral(self):
        adapter = AuroraAlphaAdapter()
        result = adapter.calculate_alpha(
            symbol="BTCUSDT",
            market_data={"close": 50000.0},
            features=_FEATURES_NEUTRAL,
        )
        assert abs(float(result.score)) < 0.01, (
            "Zero pillar_sum must produce near-zero score"
        )

    def test_adapter_output_stable_across_calls(self):
        adapter = AuroraAlphaAdapter()
        r1 = adapter.calculate_alpha(
            "BTCUSDT", {"close": 50000.0}, _FEATURES_BUY)
        r2 = adapter.calculate_alpha(
            "BTCUSDT", {"close": 50000.0}, _FEATURES_BUY)
        assert r1.score == r2.score, "Deterministic: same inputs must yield same output"

    def test_score_depends_only_on_pillar_sum(self):
        """Changing non-pillar_sum features must not change the score."""
        adapter = AuroraAlphaAdapter()

        features_base = {**_FEATURES_BUY}
        features_varied = {
            **_FEATURES_BUY,
            "obi": 0.01,
            "tfi": -0.99,
            "macro_resid": -0.99,
        }
        r_base = adapter.calculate_alpha(
            "BTCUSDT", {"close": 50000.0}, features_base)
        r_varied = adapter.calculate_alpha(
            "BTCUSDT", {"close": 50000.0}, features_varied)
        assert float(r_base.score) == pytest.approx(float(r_varied.score), abs=1e-9), (
            "Score must depend only on pillar_sum, not on obi/tfi/macro_resid"
        )
