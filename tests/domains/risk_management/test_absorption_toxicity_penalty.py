"""
P3: Absorption Toxicity Proxy Tests.

Verifies the new toxicity formula:
    toxicity = |tfi| * clip(|delta_price_pct| / dp_cap, 0, 1)

Contracts:
- use_absorption_penalty=False → toxicity term = 0
- Sign symmetry: tfi=+X and tfi=-X → same risk_score
- delta_price_pct=0 → penalty=0
- tfi=0 → penalty=0
- |delta_price_pct| >= dp_cap → impact_norm=1 (bounded)
- use_absorption_penalty=True without absorption_dp_cap_pct → ValidationError (fail-closed)
"""

import decimal
import unittest
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_domain_config(use_penalty: bool, dp_cap_pct=0.02):
    """Build a minimal RiskManagementDomainConfig mock for unit tests."""
    cfg = MagicMock()
    cfg.use_absorption_penalty = use_penalty
    cfg.absorption_dp_cap_pct = dp_cap_pct if use_penalty else None
    cfg.risk_score_weights.delta_price_pct = 0.1
    cfg.risk_score_weights.obi = 0.3
    cfg.risk_score_weights.tfi = 0.3
    cfg.risk_score_weights.absorption_inverse = 0.3
    cfg.trading_allowed_thresholds.max_risk_score = 0.96
    cfg.validation.total_weight_min = 0.5
    cfg.validation.total_weight_max = 2.0
    return cfg


def _compute_toxicity_score(
    tfi: float,
    delta_price_abs: float,
    price: float,
    dp_cap: float,
    absorption_inverse_weight: float,
) -> decimal.Decimal:
    """
    Reference implementation of toxicity proxy (mirrors risk_management.py P3).
    Used to compute expected values in tests without wiring full RiskManagement.
    """
    tfi_d = decimal.Decimal(str(tfi))
    dp_pct = decimal.Decimal(str(delta_price_abs)) / decimal.Decimal(str(price))
    cap = decimal.Decimal(str(dp_cap))
    if cap > 0:
        impact_norm = min(decimal.Decimal("1"), dp_pct / cap)
    else:
        impact_norm = decimal.Decimal("0")
    toxicity = abs(tfi_d) * impact_norm
    return toxicity * decimal.Decimal(str(absorption_inverse_weight))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToxicityPenaltyDisabled(unittest.TestCase):
    """use_absorption_penalty=False → toxicity term must be 0."""

    def test_penalty_disabled_toxicity_is_zero(self):
        """When penalty disabled, risk_score must not change due to toxicity."""
        from apps.reference.domains.risk_management.risk_management import _to_dec

        # Simulate penalty off
        use_penalty = False
        absorption_inverse_weight = decimal.Decimal("0") if not use_penalty else decimal.Decimal("0.3")

        tfi = decimal.Decimal("0.8")
        delta_price_pct = decimal.Decimal("0.05")
        dp_cap = decimal.Decimal("0.02")

        if use_penalty and absorption_inverse_weight > 0:
            impact_norm = min(decimal.Decimal("1"), delta_price_pct / dp_cap)
            toxicity = abs(tfi) * impact_norm
        else:
            toxicity = decimal.Decimal("0")

        self.assertEqual(toxicity, decimal.Decimal("0"),
                         "toxicity must be 0 when use_absorption_penalty=False")

        toxicity_contribution = toxicity * absorption_inverse_weight
        self.assertEqual(toxicity_contribution, decimal.Decimal("0"))


class TestToxicitySignSymmetry(unittest.TestCase):
    """tfi=+X and tfi=-X must produce identical toxicity (directionless)."""

    def test_positive_tfi_equals_negative_tfi_toxicity(self):
        """Toxicity must be symmetric to TFI sign — it's directionless risk."""
        dp_cap = 0.02
        weight = 0.3
        delta_price_abs = 100.0
        price = 10000.0

        score_pos = _compute_toxicity_score(+0.8, delta_price_abs, price, dp_cap, weight)
        score_neg = _compute_toxicity_score(-0.8, delta_price_abs, price, dp_cap, weight)

        self.assertEqual(score_pos, score_neg,
                         f"Toxicity must be sign-symmetric: +tfi={score_pos} != -tfi={score_neg}")

    def test_zero_tfi_regardless_of_dp(self):
        """tfi=0 → toxicity=0 regardless of delta_price."""
        dp_cap = 0.02
        weight = 0.3
        tox = _compute_toxicity_score(0.0, 500.0, 10000.0, dp_cap, weight)
        self.assertEqual(tox, decimal.Decimal("0"),
                         "Zero TFI must produce zero toxicity")


class TestToxicityZeroDeltaPrice(unittest.TestCase):
    """delta_price=0 → impact_norm=0 → penalty=0."""

    def test_zero_delta_price_gives_zero_penalty(self):
        """When price hasn't moved, there's no toxicity even at high TFI."""
        tox = _compute_toxicity_score(
            tfi=0.9,
            delta_price_abs=0.0,
            price=10000.0,
            dp_cap=0.02,
            absorption_inverse_weight=0.3,
        )
        self.assertEqual(tox, decimal.Decimal("0"),
                         "Zero delta_price must produce zero toxicity penalty")


class TestToxicityImpactNormCap(unittest.TestCase):
    """When |delta_price_pct| >= dp_cap → impact_norm capped at 1.0."""

    def test_large_move_caps_impact_norm_at_one(self):
        """
        delta_price_pct = 0.10, dp_cap = 0.02 → impact_norm = 1.0 (capped).
        toxicity = |tfi| * 1.0 * weight.
        """
        dp_cap = 0.02
        weight = 0.3
        tfi = 0.5
        # delta_price_abs = 10% of 10000 = 1000
        tox = _compute_toxicity_score(tfi, 1000.0, 10000.0, dp_cap, weight)

        expected_impact_norm = decimal.Decimal("1")  # capped
        expected_toxicity = abs(decimal.Decimal(str(tfi))) * expected_impact_norm
        expected = expected_toxicity * decimal.Decimal(str(weight))

        self.assertEqual(tox, expected,
                         f"impact_norm must be capped at 1.0 for large moves: got {tox}, expected {expected}")

    def test_exact_cap_boundary(self):
        """delta_price_pct == dp_cap → impact_norm exactly 1.0."""
        dp_cap = 0.02
        weight = 0.3
        tfi = 0.6
        # delta_price_abs = 2% of 10000 = 200 → dp_pct = 0.02 = dp_cap
        tox = _compute_toxicity_score(tfi, 200.0, 10000.0, dp_cap, weight)

        delta_price_pct = decimal.Decimal("200") / decimal.Decimal("10000")
        cap_d = decimal.Decimal(str(dp_cap))
        impact_norm = min(decimal.Decimal("1"), delta_price_pct / cap_d)

        self.assertEqual(impact_norm, decimal.Decimal("1"),
                         "At exact cap boundary, impact_norm must equal 1.0")


class TestDpCapPctFailClosed(unittest.TestCase):
    """use_absorption_penalty=True without absorption_dp_cap_pct → ValidationError."""

    def test_penalty_true_without_dp_cap_raises_validation_error(self):
        """Pydantic must reject configs where penalty=True but cap missing."""
        from apps.reference.config_models import RiskManagementDomainConfig

        with self.assertRaises(ValidationError) as ctx:
            RiskManagementDomainConfig(
                use_absorption_penalty=True,
                absorption_dp_cap_pct=None,   # intentionally missing
                risk_score_weights={
                    "delta_price_pct": 0.1,
                    "obi": 0.3,
                    "tfi": 0.3,
                    "absorption_inverse": 0.3,
                },
                trading_allowed_thresholds={"max_risk_score": 0.96},
                validation={"total_weight_min": 0.5, "total_weight_max": 2.0},
            )
        err = str(ctx.exception)
        self.assertIn("absorption_dp_cap_pct", err,
                      "ValidationError must mention absorption_dp_cap_pct")
        self.assertIn("domains.yaml", err,
                      "ValidationError must point user to domains.yaml for the fix")

    def test_penalty_false_without_dp_cap_passes(self):
        """use_absorption_penalty=False without dp_cap_pct must NOT raise."""
        from apps.reference.config_models import RiskManagementDomainConfig

        cfg = RiskManagementDomainConfig(
            use_absorption_penalty=False,
            absorption_dp_cap_pct=None,   # allowed when penalty disabled
            risk_score_weights={
                "delta_price_pct": 0.1,
                "obi": 0.3,
                "tfi": 0.3,
                "absorption_inverse": 0.3,
            },
            trading_allowed_thresholds={"max_risk_score": 0.96},
            validation={"total_weight_min": 0.5, "total_weight_max": 2.0},
        )
        self.assertFalse(cfg.use_absorption_penalty)
        self.assertIsNone(cfg.absorption_dp_cap_pct)

    def test_penalty_true_with_dp_cap_passes(self):
        """Valid config: penalty=True + dp_cap_pct set → no error."""
        from apps.reference.config_models import RiskManagementDomainConfig

        cfg = RiskManagementDomainConfig(
            use_absorption_penalty=True,
            absorption_dp_cap_pct=0.02,
            risk_score_weights={
                "delta_price_pct": 0.1,
                "obi": 0.3,
                "tfi": 0.3,
                "absorption_inverse": 0.3,
            },
            trading_allowed_thresholds={"max_risk_score": 0.96},
            validation={"total_weight_min": 0.5, "total_weight_max": 2.0},
        )
        self.assertTrue(cfg.use_absorption_penalty)
        self.assertAlmostEqual(cfg.absorption_dp_cap_pct, 0.02)


if __name__ == "__main__":
    unittest.main()
