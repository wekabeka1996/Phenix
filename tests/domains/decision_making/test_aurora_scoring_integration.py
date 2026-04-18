"""Package 2 proof-gap integration tests.

Covers five edge cases that were unproven after the Package 2 math/policy
decomposition:

A. Compound: regime widening + partial shield attenuation + admission floor lift
B. Asymmetric thresholds (side-bias) + hysteresis hold-vs-flip boundary
C. neutral_threshold=None fallback under active regime widening
D. linear_score bypass path equivalence with features["pillar_sum"] path
E. psi_vector["final_exposure"] — pin its value and relationship to sizing_score

These tests do NOT prove live runtime equivalence. They prove unit/integration
behavior of the decomposed math + policy layers under the stated edge cases.
"""
from __future__ import annotations

import decimal
import pytest

from apps.reference.domains.decision_making.aurora_math import (
    apply_shield_attenuation,
    compute_aurora_math,
    AuroraMathInput,
)
from apps.reference.domains.decision_making.aurora_policy import (
    AuroraPolicyInput,
    SideBiasState,
    apply_aurora_policy,
    compute_side_bias_multipliers,
)
from apps.reference.domains.decision_making.quadratic_scoring_kernel import (
    QuadraticScoringKernel,
)

D = decimal.Decimal


# ---------------------------------------------------------------------------
# Shared kernel call helper
# ---------------------------------------------------------------------------

def _kernel(
    *,
    pillar_sum: float = 0.4,
    linear_score: float | None = None,
    base_threshold: str = "0.02",
    regime_name: str = "DEFAULT",
    regime_thresholds: dict | None = None,
    side_bias_state=None,
    neutral_threshold: str | None = "0.01",
    current_side: str = "",
    shield_fn=None,
    admission_mode: str = "quadratic",
    sizing_mode: str = "quadratic",
    admission_shield_floor: float = 0.0,
    score_multiplier: float = 1.0,
):
    if regime_thresholds is None:
        regime_thresholds = {"DEFAULT": 1.0}
    features = {} if linear_score is not None else {"pillar_sum": pillar_sum}
    return QuadraticScoringKernel.compute(
        symbol="ETHUSDT",
        features=features,
        warmup_readiness={},
        price=D("100"),
        signal_weights={},
        feature_neutrals={},
        essential_features=[],
        base_threshold=D(base_threshold),
        regime_name=regime_name,
        regime_thresholds=regime_thresholds,
        side_bias_state=side_bias_state,
        direction_strength_cfg={},
        delta_price_cap_pct=D("0.02"),
        neutral_threshold=D(
            neutral_threshold) if neutral_threshold is not None else None,
        current_side=current_side,
        shield_fn=shield_fn,
        admission_mode=admission_mode,
        sizing_mode=sizing_mode,
        admission_shield_floor=admission_shield_floor,
        score_multiplier=score_multiplier,
        linear_score=linear_score,
    )


# ---------------------------------------------------------------------------
# Test A — compound: regime widening + partial shield + admission floor lift
# ---------------------------------------------------------------------------

class TestCompoundRegimeShieldFloor:
    """Prove that regime widening, partial shield attenuation, and admission
    floor lift interact correctly when all three are active simultaneously."""

    def test_admission_and_sizing_diverge_under_compound_conditions(self):
        """
        Setup:
          pillar_sum=0.4  → s_clamped=0.4
          quadratic: admission_pre_shield = 0.4² = 0.16
          shield_mult=0.3, admission_shield_floor=0.75
          → admission_shield_mult = max(0.3, 0.75) = 0.75
          → decision_score = 0.16 * 0.75 = 0.12
          → sizing_score   = 0.16 * 0.30 = 0.048

          regime_factor=2.0 → signal_threshold = 0.02 * 2.0 = 0.04
          0.12 >= 0.04 → side = "buy"

        Proves: regime widening and floor lift are both active; decision_score
        and sizing_score differ; regime-widened threshold is still crossed.
        """
        result = _kernel(
            pillar_sum=0.4,
            regime_thresholds={"DEFAULT": 2.0},
            shield_fn=lambda *_: (0.3, ["PARTIAL_SHIELD"]),
            admission_shield_floor=0.75,
        )

        assert not result.deferred
        assert result.side == "buy"

        # decision_score = 0.16 * 0.75 = 0.12
        assert float(result.decision_score) == pytest.approx(0.12, abs=1e-7)
        # sizing_score = 0.16 * 0.30 = 0.048
        assert float(result.sizing_score) == pytest.approx(0.048, abs=1e-7)
        # admission_shield_multiplier = floor wins = 0.75
        assert float(result.admission_shield_multiplier) == pytest.approx(
            0.75, abs=1e-7)
        # threshold_factor = 2.0 (regime widening applied)
        assert result.threshold_factor == D("2")
        # thr_buy widened: 0.02 * 2.0 = 0.04
        assert result.thr_buy == pytest.approx(D("0.04"), abs=D("1e-8"))

    def test_regime_widening_blocks_weak_signal_despite_floor(self):
        """
        With regime_factor=2.0 and base_threshold=0.02 → thr_buy=0.04.
        pillar_sum=0.1 → decision_score = 0.1² * 0.75 = 0.0075
        0.0075 < 0.04 → side = "" (blocked by widened threshold).

        Proves: regime widening can block a signal that the floor helped
        partially recover — the widened threshold is the binding constraint.
        """
        result = _kernel(
            pillar_sum=0.1,
            regime_thresholds={"DEFAULT": 2.0},
            shield_fn=lambda *_: (0.3, ["PARTIAL_SHIELD"]),
            admission_shield_floor=0.75,
        )

        assert not result.deferred
        assert result.side == ""
        # decision_score = 0.01 * 0.75 = 0.0075
        assert float(result.decision_score) == pytest.approx(0.0075, abs=1e-7)

    def test_hard_veto_overrides_floor_even_with_regime_widening(self):
        """
        shield_mult=0.0 + admission_shield_floor=0.75 + regime_factor=2.0.
        Hard veto must zero both scores regardless of floor and regime.

        Proves: the hard-veto branch in apply_shield_attenuation is not
        bypassed when regime widening is also active.
        """
        result = _kernel(
            pillar_sum=0.5,
            regime_thresholds={"DEFAULT": 2.0},
            shield_fn=lambda *_: (0.0, ["HARD_VETO"]),
            admission_shield_floor=0.75,
        )

        assert not result.deferred
        assert result.side == ""
        assert result.decision_score == D("0")
        assert result.sizing_score == D("0")
        assert result.admission_shield_multiplier == D("0")


# ---------------------------------------------------------------------------
# Test B — asymmetric thresholds + hysteresis hold-vs-flip boundary
# ---------------------------------------------------------------------------

class TestAsymmetricThresholdsHysteresis:
    """Prove that hysteresis transitions are correct when thr_buy != thr_sell
    due to side-bias widening."""

    @staticmethod
    def _biased_sell_state() -> SideBiasState:
        """Sell-heavy bias: 17 sell / 3 buy out of 20 total.
        sell_share=0.85 > target=0.72
        excess=0.13, max_excess=0.28
        scaling=0.13/0.28 ≈ 0.4643
        sell_mult = 1 + 0.25 * 0.4643 ≈ 1.1161
        → thr_sell ≈ 0.02 * 1.1161 ≈ 0.02232
        → thr_buy  = 0.02 (no buy penalty)
        """
        return SideBiasState(
            buy_count=3, sell_count=17, min_intents=18,
            target_ratio=0.72, penalty_factor=0.25,
        )

    def test_sell_bias_blocks_entry_below_widened_threshold(self):
        """A score that crosses the base sell threshold (-0.02) but NOT the
        widened threshold (-0.02232) must be blocked from entering sell.

        pillar_sum = -sqrt(0.021) ≈ -0.14491 → decision_score ≈ -0.021
        -0.021 is NOT <= -0.02232 → stays neutral (from neutral, no sell entry).

        Proves: asymmetric thr_sell blocks an entry that base threshold would allow.
        """
        bias = self._biased_sell_state()
        buy_mult, sell_mult = compute_side_bias_multipliers(bias)
        assert sell_mult > D("1.0"), "pre-condition: bias must widen sell"

        result = _kernel(
            pillar_sum=-0.145,  # quadratic ≈ -0.021025
            side_bias_state=bias,
            current_side="",
        )
        assert not result.deferred
        # The base threshold 0.02 would be crossed, but the widened sell
        # threshold (≈0.02232) is not crossed.
        assert result.side == "", (
            f"Expected neutral (widened sell threshold blocks entry), "
            f"got side={result.side}, thr_sell={result.thr_sell}, "
            f"decision_score={result.decision_score}"
        )
        # Confirm the threshold was actually widened
        assert result.thr_sell > D("0.02")

    def test_sell_bias_does_not_affect_buy_threshold(self):
        """When sell is overloaded, thr_buy must remain at base threshold.

        A buy signal that crosses 0.02 must still enter buy.
        """
        bias = self._biased_sell_state()

        result = _kernel(
            pillar_sum=0.4,   # decision_score = 0.16 >> 0.02
            side_bias_state=bias,
            current_side="",
        )
        assert not result.deferred
        assert result.side == "buy"
        # Buy threshold unaffected
        assert result.thr_buy == D("0.02")

    def test_hysteresis_hold_sell_near_flip_with_asymmetric_thresholds(self):
        """With current_side="sell" and asymmetric thresholds:
        - hold condition (sell): score <= -thr_neutral
        - flip condition: score >= thr_buy (unaffected = 0.02)

        A moderately negative score (well below -thr_neutral=0.01) must hold
        sell even though thr_sell is widened.

        pillar_sum=-0.4 → decision_score=-0.16 << -0.01 → hold:sell
        """
        bias = self._biased_sell_state()

        result = _kernel(
            pillar_sum=-0.4,
            side_bias_state=bias,
            current_side="sell",
            neutral_threshold="0.01",
        )
        assert not result.deferred
        assert result.side == "sell"
        assert "hold:sell" in result.why_chain[0]


# ---------------------------------------------------------------------------
# Test C — neutral_threshold=None fallback under regime widening
# ---------------------------------------------------------------------------

class TestNeutralThresholdNoneFallback:
    """Prove the behavior when neutral_threshold is omitted and regime is active.

    In aurora_policy.apply_aurora_policy():
        thr_neutral = inp.neutral_threshold if inp.neutral_threshold is not None else thr_buy

    After regime widening: thr_buy = base * factor. With neutral_threshold=None,
    the hysteresis neutral band grows proportionally with regime.
    """

    def test_none_neutral_uses_widened_thr_buy_as_neutral(self):
        """With base_threshold=0.02, regime_factor=2.0:
        thr_buy = 0.04. neutral_threshold=None → thr_neutral = 0.04.

        current_side="buy", decision_score=0.02:
        - With explicit neutral_threshold=0.01: 0.02 >= 0.01 → hold:buy
        - With neutral_threshold=None → thr_neutral=0.04: 0.02 < 0.04 → exit:neutral

        Proves: omitting neutral_threshold silently widens the hysteresis band
        proportionally to the regime multiplier.
        """
        # Explicit neutral=0.01: holds buy at score=0.02
        result_with_neutral = _kernel(
            pillar_sum=0.142,   # quadratic ≈ 0.02 decision_score
            regime_thresholds={"DEFAULT": 2.0},
            current_side="buy",
            neutral_threshold="0.01",
        )
        assert not result_with_neutral.deferred
        assert result_with_neutral.side == "buy", "pre-condition: holds with explicit neutral"

        # Same inputs, neutral_threshold=None: exits buy
        result_no_neutral = _kernel(
            pillar_sum=0.142,
            regime_thresholds={"DEFAULT": 2.0},
            current_side="buy",
            neutral_threshold=None,
        )
        assert not result_no_neutral.deferred
        assert result_no_neutral.side == "", (
            "Expected exit to neutral when neutral_threshold=None causes "
            f"thr_neutral to equal widened thr_buy={result_no_neutral.thr_buy}; "
            f"got side={result_no_neutral.side}"
        )

    def test_none_neutral_with_no_regime_uses_base_threshold_as_neutral(self):
        """With regime_factor=1.0 (no widening):
        thr_buy = base = 0.02. neutral_threshold=None → thr_neutral = 0.02.

        Proving that when regime_factor=1.0, neutral band equals base threshold —
        any score below 0.02 exits the buy side.
        """
        result = _kernel(
            pillar_sum=0.10,   # quadratic=0.01, below thr_neutral=0.02 when None
            regime_thresholds={"DEFAULT": 1.0},
            current_side="buy",
            neutral_threshold=None,
        )
        assert not result.deferred
        # 0.01 < 0.02 (thr_neutral when None=base) → exit
        assert result.side == ""

    def test_policy_layer_neutral_threshold_none_directly(self):
        """Direct policy-layer test confirming the fallback at the source.

        neutral_threshold=None with base=0.02 and regime_factor=1.5:
        thr_buy = 0.03. thr_neutral fallback = 0.03.
        decision_score=0.025 in current_side="buy" → exit (0.025 < 0.03).
        """
        pol_in = AuroraPolicyInput(
            decision_score=0.025,
            sizing_score=0.025,
            base_threshold=D("0.02"),
            regime_name="DEFAULT",
            regime_thresholds={"DEFAULT": 1.5},
            side_bias_state=None,
            neutral_threshold=None,
            current_side="buy",
        )
        pol_out = apply_aurora_policy(pol_in)
        assert not pol_out.deferred
        assert pol_out.thr_buy == D("0.03")  # 0.02 * 1.5
        assert pol_out.side == ""  # 0.025 < thr_neutral=thr_buy=0.03 → exit


# ---------------------------------------------------------------------------
# Test D — linear_score bypass equivalence
# ---------------------------------------------------------------------------

class TestLinearScoreBypassEquivalence:
    """Prove that passing linear_score as an explicit arg produces identical
    numeric output to passing the same value via features['pillar_sum']."""

    @pytest.mark.parametrize("value", [0.4, -0.3, 0.0, 0.01, -0.99, 0.75])
    def test_both_paths_produce_identical_scores(self, value: float):
        """The two input resolution branches must be numerically equivalent
        for the same value. Proves the bypass path is not a divergent code path.
        """
        via_features = _kernel(pillar_sum=value)
        via_arg = _kernel(linear_score=value)

        assert via_features.deferred == via_arg.deferred, (
            f"deferred state mismatch for value={value}"
        )
        if via_features.deferred:
            return  # both deferred for the same reason; no further checks

        assert via_features.decision_score == via_arg.decision_score, (
            f"decision_score mismatch: features={via_features.decision_score} "
            f"arg={via_arg.decision_score}"
        )
        assert via_features.sizing_score == via_arg.sizing_score
        assert via_features.side == via_arg.side
        assert via_features.raw_score == via_arg.raw_score

    def test_bypass_sets_source_to_arg(self):
        """psi_vector["source"] must reflect which input path was taken."""
        via_features = _kernel(pillar_sum=0.4)
        via_arg = _kernel(linear_score=0.4)

        assert via_features.psi_vector.get("source") == "feature:pillar_sum"
        assert via_arg.psi_vector.get("source") == "arg"

    def test_bypass_does_not_require_pillar_sum_in_features(self):
        """linear_score path must not defer even when features is empty."""
        result = _kernel(linear_score=0.4)
        assert not result.deferred
        assert result.side == "buy"


# ---------------------------------------------------------------------------
# Test E — psi_vector["final_exposure"] is pinned to sizing_score
# ---------------------------------------------------------------------------

class TestPsiVectorFinalExposure:
    """Pin that psi_vector['final_exposure'] equals sizing_score, not
    decision_score, so the field cannot drift silently across refactors.

    Current mapping (quadratic_scoring_kernel.py line ~283):
        "final_exposure": math_out.sizing_score
    This is also what 'raw_exposure' in shield_breakdown tracks via sizing_pre_shield.
    """

    def test_final_exposure_equals_sizing_score_no_shield(self):
        """With no shield (multiplier=1.0) and coupled admission/sizing:
        decision_score == sizing_score == final_exposure.
        """
        result = _kernel(pillar_sum=0.4)
        psi = result.psi_vector

        assert "final_exposure" in psi, "final_exposure must be present in psi_vector"
        assert psi["final_exposure"] == pytest.approx(
            float(result.sizing_score), abs=1e-9
        )
        # With no shield decoupling, all three are equal
        assert psi["final_exposure"] == pytest.approx(
            float(result.decision_score), abs=1e-9
        )

    def test_final_exposure_tracks_sizing_score_not_decision_score_when_decoupled(self):
        """With admission_shield_floor lifting the admission multiplier above the
        raw shield, decision_score != sizing_score.

        final_exposure must track sizing_score (the non-floored path), NOT decision_score.
        """
        result = _kernel(
            pillar_sum=0.4,
            shield_fn=lambda *_: (0.3, ["PARTIAL"]),
            admission_shield_floor=0.75,
        )
        psi = result.psi_vector

        # Verify the decoupling happened
        assert result.decision_score != result.sizing_score, (
            "pre-condition: scores must be decoupled for this test to be meaningful"
        )

        # pin final_exposure == sizing_score
        assert psi["final_exposure"] == pytest.approx(
            float(result.sizing_score), abs=1e-9
        ), (
            f"final_exposure={psi['final_exposure']} must equal "
            f"sizing_score={result.sizing_score}, not decision_score={result.decision_score}"
        )
        # pin final_exposure != decision_score when decoupled
        assert psi["final_exposure"] != pytest.approx(
            float(result.decision_score), abs=1e-9
        )

    def test_psi_vector_required_fields_complete(self):
        """Regression guard: all expected psi_vector keys must be present."""
        result = _kernel(
            pillar_sum=0.4,
            shield_fn=lambda *_: (0.6, ["SHIELD"]),
        )
        psi = result.psi_vector

        required = {
            "scoring_engine", "source", "s_linear", "multiplier",
            "s_scaled_raw", "s_clamped", "clamped",
            "admission_mode", "sizing_mode",
            "admission_pre_shield", "sizing_pre_shield",
            "decision_score", "sizing_score",
            "shield_multiplier", "shield_reasons",
            "final_exposure",
            "threshold_factor", "thr_buy", "thr_sell",
            "buy_bias_mult", "sell_bias_mult", "side_why",
        }
        missing = required - set(psi.keys())
        assert not missing, f"psi_vector missing keys: {missing}"
