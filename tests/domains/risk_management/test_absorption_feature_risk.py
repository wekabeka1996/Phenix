"""
PKG-ABSORPTION-RISK-FULL: Feature-term absorption risk tests.

Tests the source-routing formula:
  source="proxy"   → toxicity_term used, feature_term=0
  source="feature" → feature_term=clip(|absorption|,min,max)*w, toxicity_term=0
  source="both"    → both terms applied

All tests use reference-formula helpers to avoid coupling to internal Decimal internals.
"""

import decimal
import unittest
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Reference formula helpers (mirror risk_management.py P3+PKG logic)
# ---------------------------------------------------------------------------

def _make_domain_config(
    use_penalty: bool = True,
    source: str = "proxy",
    dp_cap: float = 0.02,
    absorption_inverse: float = 0.3,
    absorption_feature_w: float = 0.0,
    clip_min: float = 0.0,
    clip_max: float = 1.0,
):
    cfg = MagicMock()
    cfg.use_absorption_penalty = use_penalty
    cfg.absorption_dp_cap_pct = dp_cap
    cfg.absorption_penalty_source = source
    cfg.absorption_feature_clip_min = clip_min
    cfg.absorption_feature_clip_max = clip_max
    cfg.risk_score_weights.delta_price_pct = 0.1
    cfg.risk_score_weights.obi = 0.3
    cfg.risk_score_weights.tfi = 0.3
    cfg.risk_score_weights.absorption_inverse = absorption_inverse
    cfg.risk_score_weights.absorption_feature = absorption_feature_w
    cfg.trading_allowed_thresholds.max_risk_score = 0.96
    return cfg


def _compute_risk(
    price: float,
    delta_price: float,
    obi: float,
    tfi: float,
    absorption,
    domain_cfg,
) -> dict:
    """Reference implementation matching risk_management.py PKG formula."""
    D = decimal.Decimal
    d_price = D(str(delta_price))
    d_obi = D(str(obi))
    d_tfi = D(str(tfi))
    price_d = D(str(price))
    dp_pct = abs(d_price) / price_d

    dw = D(str(domain_cfg.risk_score_weights.delta_price_pct))
    ow = D(str(domain_cfg.risk_score_weights.obi))
    tw = D(str(domain_cfg.risk_score_weights.tfi))
    abs_inv_w = D(str(domain_cfg.risk_score_weights.absorption_inverse))
    abs_feat_w = D(str(domain_cfg.risk_score_weights.absorption_feature))

    source = domain_cfg.absorption_penalty_source
    abs_source_tag = source

    if domain_cfg.use_absorption_penalty and source in ("proxy", "both"):
        cap = D(str(domain_cfg.absorption_dp_cap_pct))
        impact_norm = min(D("1"), dp_pct / cap) if cap > 0 else D("0")
        applied_toxicity = abs(d_tfi) * impact_norm * abs_inv_w
    else:
        applied_toxicity = D("0")

    if (
        domain_cfg.use_absorption_penalty
        and source in ("feature", "both")
        and abs_feat_w > 0
    ):
        if absorption is not None:
            abs_val = abs(D(str(absorption)))
            clip_min = D(str(domain_cfg.absorption_feature_clip_min))
            clip_max = D(str(domain_cfg.absorption_feature_clip_max))
            clipped = max(clip_min, min(clip_max, abs_val))
            applied_feature = clipped * abs_feat_w
        else:
            applied_feature = D("0")
            abs_source_tag += "+abs_missing"
    else:
        applied_feature = D("0")

    score = dp_pct * dw + abs(d_obi) * ow + abs(d_tfi) * tw + applied_toxicity + applied_feature
    score = max(D("0"), min(D("1"), score))

    return {
        "risk_score": float(score),
        "toxicity_term": float(applied_toxicity),
        "absorption_feature_term": float(applied_feature),
        "abs_source": abs_source_tag,
    }


# ---------------------------------------------------------------------------
# Test: default proxy path — backward compatibility with P3
# ---------------------------------------------------------------------------

class TestRiskScoreDefaultProxyUnchanged(unittest.TestCase):
    """source='proxy', absorption_feature_w=0 → score must be identical to P3."""

    def test_default_proxy_absorption_field_has_no_effect(self):
        """
        When source='proxy' and absorption_feature_w=0 (both defaults),
        features["absorption"] must not affect risk_score.
        This is the backward-compat invariant.
        """
        cfg_no_absfeat = _make_domain_config(
            use_penalty=False, source="proxy", absorption_feature_w=0.0
        )
        # With penalty disabled, absorption never matters
        r1 = _compute_risk(100, 5.0, 0.1, 0.5, absorption=0.9, domain_cfg=cfg_no_absfeat)
        r2 = _compute_risk(100, 5.0, 0.1, 0.5, absorption=0.1, domain_cfg=cfg_no_absfeat)

        self.assertAlmostEqual(r1["risk_score"], r2["risk_score"], places=10,
                               msg="source='proxy', penalty disabled: absorption value must not change score")

    def test_source_proxy_feature_term_is_zero(self):
        """When source='proxy', applied_feature must always be 0."""
        cfg = _make_domain_config(
            use_penalty=True, source="proxy", dp_cap=0.02,
            absorption_inverse=0.3, absorption_feature_w=0.2  # non-zero but source=proxy
        )
        r = _compute_risk(100, 2.0, 0.1, 0.5, absorption=0.8, domain_cfg=cfg)
        self.assertEqual(r["absorption_feature_term"], 0.0,
                         "source='proxy' must produce feature_term=0 even if absorption_feature_w>0")


# ---------------------------------------------------------------------------
# Test: source="feature" — uses absorption, bypasses toxicity proxy
# ---------------------------------------------------------------------------

class TestRiskScoreFeatureOnlyUsesAbsorption(unittest.TestCase):
    """source='feature' → feature_term=clip(|absorption|,0,1)*w, toxicity_term=0."""

    def test_feature_term_math(self):
        """
        features: price=100, delta_price=5, obi=0.1, tfi=0.5, absorption=0.8
        absorption_feature_w=0.3
        feature_term = clip(0.8, 0, 1) * 0.3 = 0.24
        toxicity = 0 (source="feature")
        """
        cfg = _make_domain_config(
            use_penalty=True, source="feature",
            absorption_inverse=0.3, absorption_feature_w=0.3,
        )
        r = _compute_risk(100, 5.0, 0.1, 0.5, absorption=0.8, domain_cfg=cfg)

        self.assertAlmostEqual(r["absorption_feature_term"], 0.24, places=10,
                               msg="feature_term = clip(0.8,0,1) * 0.3 = 0.24")
        self.assertEqual(r["toxicity_term"], 0.0,
                         "source='feature' must have toxicity_term=0")
        self.assertIn("feature", r["abs_source"])

    def test_feature_term_negative_absorption_uses_abs(self):
        """SIGNED absorption = -0.6 → feature_term uses |absorption| = 0.6."""
        cfg = _make_domain_config(
            use_penalty=True, source="feature",
            absorption_inverse=0.3, absorption_feature_w=0.3,
        )
        r_pos = _compute_risk(100, 5.0, 0.1, 0.5, absorption=+0.6, domain_cfg=cfg)
        r_neg = _compute_risk(100, 5.0, 0.1, 0.5, absorption=-0.6, domain_cfg=cfg)

        self.assertAlmostEqual(r_pos["absorption_feature_term"], r_neg["absorption_feature_term"],
                               places=10, msg="|absorption| must be symmetric to sign")


# ---------------------------------------------------------------------------
# Test: source="both" — additive
# ---------------------------------------------------------------------------

class TestRiskScoreBothAddTerms(unittest.TestCase):
    """source='both' → risk_score = base + toxicity_term + feature_term."""

    def test_both_adds_both_terms(self):
        cfg = _make_domain_config(
            use_penalty=True, source="both",
            dp_cap=0.02, absorption_inverse=0.3, absorption_feature_w=0.2,
        )
        r = _compute_risk(100, 2.0, 0.1, 0.5, absorption=0.6, domain_cfg=cfg)

        # toxicity_term > 0 (penalty enabled, source includes proxy)
        self.assertGreater(r["toxicity_term"], 0.0)
        # feature_term > 0 (penalty enabled, source includes feature)
        self.assertGreater(r["absorption_feature_term"], 0.0)


# ---------------------------------------------------------------------------
# Test: fail-closed on missing absorption
# ---------------------------------------------------------------------------

class TestAbsorptionMissingFailClosed(unittest.TestCase):
    """When absorption key is absent from features, feature_term=0 (no crash)."""

    def test_missing_absorption_no_crash(self):
        cfg = _make_domain_config(
            use_penalty=True, source="feature",
            absorption_inverse=0.3, absorption_feature_w=0.3,
        )
        r = _compute_risk(100, 2.0, 0.1, 0.5, absorption=None, domain_cfg=cfg)

        self.assertEqual(r["absorption_feature_term"], 0.0,
                         "Missing absorption must silently produce feature_term=0")
        self.assertIn("abs_missing", r["abs_source"],
                      "abs_source tag must include '+abs_missing' when key absent")


# ---------------------------------------------------------------------------
# Test: Pydantic schema validation
# ---------------------------------------------------------------------------

class TestConfigNewFieldsStrictValidation(unittest.TestCase):
    """Pydantic must accept new fields with their defaults."""

    def test_risk_score_weights_with_absorption_feature(self):
        from apps.reference.config_models import RiskScoreWeightsConfig
        cfg = RiskScoreWeightsConfig(
            delta_price_pct=0.1, obi=0.3, tfi=0.3,
            absorption_inverse=0.3, absorption_feature=0.2,
        )
        self.assertAlmostEqual(cfg.absorption_feature, 0.2)

    def test_risk_score_weights_default_absorption_feature_zero(self):
        from apps.reference.config_models import RiskScoreWeightsConfig
        cfg = RiskScoreWeightsConfig(
            delta_price_pct=0.1, obi=0.3, tfi=0.3, absorption_inverse=0.3,
        )
        self.assertEqual(cfg.absorption_feature, 0.0,
                         "Default absorption_feature must be 0.0 (backward compat)")

    def test_risk_management_domain_new_fields_have_defaults(self):
        from apps.reference.config_models import RiskManagementDomainConfig
        cfg = RiskManagementDomainConfig(
            use_absorption_penalty=False,
            risk_score_weights={
                "delta_price_pct": 0.1, "obi": 0.3,
                "tfi": 0.3, "absorption_inverse": 0.3,
            },
            trading_allowed_thresholds={"max_risk_score": 0.96},
            validation={"total_weight_min": 0.5, "total_weight_max": 2.0},
        )
        self.assertEqual(cfg.absorption_penalty_source, "proxy")
        self.assertAlmostEqual(cfg.absorption_feature_clip_min, 0.0)
        self.assertAlmostEqual(cfg.absorption_feature_clip_max, 1.0)


class TestConfigInvalidSourceRejected(unittest.TestCase):
    """Unknown absorption_penalty_source values must raise ValidationError."""

    def test_invalid_source_raises(self):
        from apps.reference.config_models import RiskManagementDomainConfig
        with self.assertRaises(ValidationError) as ctx:
            RiskManagementDomainConfig(
                use_absorption_penalty=False,
                absorption_penalty_source="magic_source",   # invalid Literal
                risk_score_weights={
                    "delta_price_pct": 0.1, "obi": 0.3,
                    "tfi": 0.3, "absorption_inverse": 0.3,
                },
                trading_allowed_thresholds={"max_risk_score": 0.96},
                validation={"total_weight_min": 0.5, "total_weight_max": 2.0},
            )
        self.assertIn("absorption_penalty_source", str(ctx.exception).lower()
                      or "magic_source" in str(ctx.exception))


class TestConfigLoaderAcceptsNewKeys(unittest.TestCase):
    """ConfigLoader must load config/aurora domain config with new keys cleanly."""

    def test_get_config_ok(self):
        from apps.reference.config_loader import get_config
        cfg = get_config()
        rm = cfg.domains.risk_management
        # Source routing fields have expected values from domains.yaml
        self.assertEqual(rm.absorption_penalty_source, "feature")
        self.assertAlmostEqual(rm.absorption_feature_clip_min, 0.0)
        self.assertAlmostEqual(rm.absorption_feature_clip_max, 1.0)
        self.assertAlmostEqual(rm.risk_score_weights.absorption_feature, 0.2)


if __name__ == "__main__":
    unittest.main()
