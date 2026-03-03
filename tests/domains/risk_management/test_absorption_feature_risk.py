"""
PKG-ABSORPTION-RISK-FULL: tests for absorption_penalty_source wiring in risk_management.

Tests cover:
1. Default proxy behavior is unchanged (absorption value must not affect score).
2. source="feature" uses only the emitted absorption value.
3. source="both" adds proxy + feature terms.
4. Missing absorption is fail-closed (feature_term=0, abs_missing flag).
5. Config validators accept new fields without extra='forbid' violation.
"""
import decimal
import pytest
from pydantic import ValidationError

from apps.reference.config_loader import get_config
from apps.reference.config_models import (
    RiskManagementDomainConfig,
    RiskScoreWeightsConfig,
    TradingAllowedThresholdsConfig,
    RiskValidationConfig,
)
from apps.reference.domains.risk_management.risk_management import RiskManagement


class _DummyFsm:
    def emit(self, *_a, **_k) -> None:
        return

    def listen(self, *_a, **_k) -> None:
        return


class _AllowGate:
    def can_open(self):
        return True, {"why": "test_allow"}


def _make_rm(
    *,
    use_penalty: bool = True,
    cap_pct: float | None = 0.02,
    source: str = "proxy",
    absorption_feature_w: float = 0.0,
    absorption_inverse_w: float = 0.3,
    clip_min: float = 0.0,
    clip_max: float = 1.0,
    max_risk: float = 1.0,
) -> RiskManagement:
    cfg = get_config()
    rm_cfg = cfg.domains.risk_management
    rm_cfg = rm_cfg.model_copy(
        update={
            "use_absorption_penalty": use_penalty,
            "absorption_dp_cap_pct": cap_pct,
            "absorption_penalty_source": source,
            "absorption_feature_clip_min": clip_min,
            "absorption_feature_clip_max": clip_max,
            "risk_score_weights": rm_cfg.risk_score_weights.model_copy(
                update={
                    "delta_price_pct": 0.1,
                    "obi": 0.3,
                    "tfi": 0.3,
                    "absorption_inverse": absorption_inverse_w,
                    "absorption_feature": absorption_feature_w,
                }
            ),
            "trading_allowed_thresholds": rm_cfg.trading_allowed_thresholds.model_copy(
                update={"max_risk_score": max_risk}
            ),
        }
    )
    cfg = cfg.model_copy(
        deep=True,
        update={
            "domains": cfg.domains.model_copy(update={"risk_management": rm_cfg}),
        },
    )
    rm = RiskManagement(_DummyFsm(), cfg)
    rm.daily_risk_state = _AllowGate()
    return rm


# ──────────────────────────────────────────────────────────────────────────────
# 1. Default proxy behavior unchanged


def test_risk_score_default_proxy_unchanged() -> None:
    """
    With source="proxy" (default) and absorption_feature=0.0, the presence of
    absorption="0.9" in features must NOT change the risk score compared to
    absorption=0.0 (or missing). The proxy-only path must be identical to old behavior.
    """
    rm = _make_rm(use_penalty=True, cap_pct=0.02,
                  source="proxy", absorption_feature_w=0.0)

    feats_with_abs = {
        "price": 100.0,
        "delta_price": 2.0,  # 2% → impact_norm = 1.0
        "obi": 0.1,
        "tfi": 0.5,
        "absorption": "0.9",
    }
    feats_no_abs = {
        "price": 100.0,
        "delta_price": 2.0,
        "obi": 0.1,
        "tfi": 0.5,
        "absorption": "0.0",
    }
    out_with = rm._calculate_risk_parameters(feats_with_abs)
    out_without = rm._calculate_risk_parameters(feats_no_abs)

    # Expected (proxy-only formula):
    # dp_pct=0.02, dw=0.1 → 0.002
    # |obi|=0.1, w=0.3  → 0.03
    # |tfi|=0.5, w=0.3  → 0.15
    # toxicity = |tfi|(0.5) * min(dp/cap, 1)(1.0) * abs_inv(0.3) = 0.15
    # total = 0.002 + 0.03 + 0.15 + 0.15 = 0.332
    expected = pytest.approx(0.332)
    assert out_with["risk_score"] == expected
    assert out_without["risk_score"] == expected

    # feature term must be zero in proxy mode
    assert out_with["risk_terms"]["absorption_feature_term"] == pytest.approx(
        0.0)
    assert out_with["risk_terms"]["abs_source"] == "proxy"


# ──────────────────────────────────────────────────────────────────────────────
# 2. source="feature" uses only emitted absorption


def test_risk_score_feature_only_uses_absorption() -> None:
    """
    With source="feature" and absorption_feature_weight=0.3, the risk score
    must include feature_term = clip(|absorption|, 0, 1) * 0.3.
    The proxy toxicity_term must be zero (not applied).
    """
    rm = _make_rm(
        use_penalty=True,
        cap_pct=0.02,
        source="feature",
        absorption_feature_w=0.3,
        absorption_inverse_w=0.3,
    )

    out = rm._calculate_risk_parameters(
        {
            "price": 100.0,
            # 5% → normally saturates impact_norm to 1.0 (but proxy is ignored)
            "delta_price": 5.0,
            "obi": 0.1,
            "tfi": 0.5,
            "absorption": "0.8",
        }
    )

    # Expected:
    # dp_pct=0.05, dw=0.1 → 0.005
    # |obi|=0.1, w=0.3  → 0.03
    # |tfi|=0.5, w=0.3  → 0.15
    # source="feature" → applied_toxicity=0
    # feature_term = clip(0.8, 0, 1) * 0.3 = 0.24
    # total = 0.005 + 0.03 + 0.15 + 0 + 0.24 = 0.425
    assert out["risk_score"] == pytest.approx(0.425)
    assert out["risk_terms"]["toxicity_term"] == pytest.approx(0.0)
    assert out["risk_terms"]["absorption_feature_term"] == pytest.approx(0.24)
    assert out["risk_terms"]["abs_source"] == "feature"


# ──────────────────────────────────────────────────────────────────────────────
# 3. source="both" adds proxy + feature terms


def test_risk_score_both_adds_terms() -> None:
    """
    With source="both", total score includes proxy toxicity_term AND feature_term.
    """
    rm = _make_rm(
        use_penalty=True,
        cap_pct=0.02,
        source="both",
        absorption_feature_w=0.3,
        absorption_inverse_w=0.3,
    )

    out = rm._calculate_risk_parameters(
        {
            "price": 100.0,
            "delta_price": 2.0,  # 2% → impact_norm = 1.0
            "obi": 0.1,
            "tfi": 0.5,
            "absorption": "0.8",
        }
    )

    # Expected:
    # dp_pct=0.02, dw=0.1 → 0.002
    # |obi|=0.1, w=0.3  → 0.030
    # |tfi|=0.5, w=0.3  → 0.150
    # toxicity_term = 0.5 * 1.0 * 0.3 = 0.150
    # feature_term  = 0.8 * 0.3         = 0.240
    # total = 0.002 + 0.030 + 0.150 + 0.150 + 0.240 = 0.572
    assert out["risk_score"] == pytest.approx(0.572)
    assert out["risk_terms"]["toxicity_term"] == pytest.approx(0.15)
    assert out["risk_terms"]["absorption_feature_term"] == pytest.approx(0.24)
    assert out["risk_terms"]["abs_source"] == "both"


# ──────────────────────────────────────────────────────────────────────────────
# 4. Fail-closed: missing absorption → feature_term=0, abs_missing flag


def test_absorption_missing_fail_closed() -> None:
    """
    If absorption is not present in features dict:
    - Must NOT crash.
    - feature_term must be 0.
    - risk_terms["abs_source"] must contain "abs_missing".
    """
    rm = _make_rm(
        use_penalty=True,
        cap_pct=0.02,
        source="feature",
        absorption_feature_w=0.3,
    )

    out = rm._calculate_risk_parameters(
        {
            "price": 100.0,
            "delta_price": 2.0,
            "obi": 0.1,
            "tfi": 0.5,
            # intentionally no "absorption" key
        }
    )

    # No crash. feature_term=0. source="feature" → applied_toxicity=0 too.
    # dp_pct=0.02 → 0.002; obi→0.03; tfi→0.15; both absorption terms=0
    # total = 0.182
    assert out["risk_score"] == pytest.approx(0.182)
    assert out["risk_terms"]["absorption_feature_term"] == pytest.approx(0.0)
    assert "abs_missing" in out["risk_terms"]["abs_source"]


# ──────────────────────────────────────────────────────────────────────────────
# 5. Config validation: new fields accepted without extra='forbid' violation


def test_config_new_fields_strict_validation() -> None:
    """
    Constructing RiskManagementDomainConfig with new PKG-ABSORPTION-RISK-FULL
    fields must succeed (not raise extra='forbid' error).
    """
    cfg = RiskManagementDomainConfig(
        use_absorption_penalty=True,
        absorption_dp_cap_pct=0.02,
        absorption_penalty_source="feature",
        absorption_feature_clip_min=0.0,
        absorption_feature_clip_max=1.0,
        risk_score_weights=RiskScoreWeightsConfig(
            delta_price_pct=0.1,
            obi=0.3,
            tfi=0.3,
            absorption_inverse=0.3,
            absorption_feature=0.2,
        ),
        trading_allowed_thresholds=TradingAllowedThresholdsConfig(
            max_risk_score=0.96),
        validation=RiskValidationConfig(
            total_weight_min=0.5, total_weight_max=2.0),
    )
    assert cfg.absorption_penalty_source == "feature"
    assert cfg.risk_score_weights.absorption_feature == 0.2
    assert cfg.absorption_feature_clip_min == 0.0
    assert cfg.absorption_feature_clip_max == 1.0


def test_config_invalid_source_rejected() -> None:
    """
    absorption_penalty_source must be one of proxy|feature|both. Unknown value must fail."""
    with pytest.raises(ValidationError):
        RiskManagementDomainConfig(
            use_absorption_penalty=True,
            absorption_dp_cap_pct=0.02,
            # type: ignore[arg-type]
            absorption_penalty_source="unknown_value",
            risk_score_weights=RiskScoreWeightsConfig(
                delta_price_pct=0.1,
                obi=0.3,
                tfi=0.3,
                absorption_inverse=0.3,
            ),
            trading_allowed_thresholds=TradingAllowedThresholdsConfig(
                max_risk_score=0.96),
            validation=RiskValidationConfig(
                total_weight_min=0.5, total_weight_max=2.0),
        )


def test_config_loader_accepts_new_keys() -> None:
    """ConfigLoader must load config/aurora without raising on new absorption keys."""
    from pathlib import Path
    from apps.reference.config_loader import ConfigLoader

    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
    rm = cfg.domains.risk_management
    # New fields should be present and loaded
    assert rm.absorption_penalty_source in {"proxy", "feature", "both"}
    assert rm.absorption_feature_clip_min >= 0.0
    assert rm.absorption_feature_clip_max > 0.0
    assert rm.risk_score_weights.absorption_feature >= 0.0
