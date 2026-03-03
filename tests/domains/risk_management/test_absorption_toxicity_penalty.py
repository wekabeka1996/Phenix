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


def _make_rm(*, use_penalty: bool, cap_pct: float | None) -> RiskManagement:
    cfg = get_config()

    rm_cfg = cfg.domains.risk_management
    rm_cfg = rm_cfg.model_copy(
        update={
            "use_absorption_penalty": use_penalty,
            "absorption_dp_cap_pct": cap_pct,
            "risk_score_weights": rm_cfg.risk_score_weights.model_copy(
                update={
                    "delta_price_pct": 0.1,
                    "obi": 0.3,
                    "tfi": 0.3,
                    "absorption_inverse": 0.3,
                }
            ),
            "trading_allowed_thresholds": rm_cfg.trading_allowed_thresholds.model_copy(
                update={"max_risk_score": 1.0}
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


def test_toxicity_penalty_disabled_is_zero() -> None:
    rm = _make_rm(use_penalty=False, cap_pct=None)
    out = rm._calculate_risk_parameters(
        {
            "price": 100.0,
            "delta_price": 2.0,  # 2%
            "obi": 0.1,
            "tfi": 0.8,
        }
    )
    assert out["risk_score"] == pytest.approx(0.272)


def test_toxicity_penalty_enabled_behavior() -> None:
    rm = _make_rm(use_penalty=True, cap_pct=0.02)

    base = {
        "price": 100.0,
        "delta_price": 2.0,  # 2% => impact_norm=1 at cap=2%
        "obi": 0.1,
    }

    out_pos = rm._calculate_risk_parameters({**base, "tfi": 0.8})
    out_neg = rm._calculate_risk_parameters({**base, "tfi": -0.8})
    assert out_pos["risk_score"] == pytest.approx(0.512)
    assert out_pos["risk_score"] == pytest.approx(out_neg["risk_score"])

    # delta_price=0 => impact_norm=0 => no toxicity penalty
    out_dp0 = rm._calculate_risk_parameters({**base, "delta_price": 0.0, "tfi": 0.8})
    assert out_dp0["risk_score"] == pytest.approx(0.27)

    # tfi=0 => toxicity=0 even if impact_norm=1
    out_tfi0 = rm._calculate_risk_parameters({**base, "tfi": 0.0})
    assert out_tfi0["risk_score"] == pytest.approx(0.032)

    # delta_price_pct > cap => impact_norm saturates to 1
    out_cap = rm._calculate_risk_parameters({**base, "delta_price": 5.0, "tfi": 0.8})
    assert out_cap["risk_score"] == pytest.approx(0.515)


def test_config_validation_requires_cap_when_penalty_enabled() -> None:
    with pytest.raises(ValidationError):
        RiskManagementDomainConfig(
            use_absorption_penalty=True,
            absorption_dp_cap_pct=None,
            risk_score_weights=RiskScoreWeightsConfig(
                delta_price_pct=0.1,
                obi=0.3,
                tfi=0.3,
                absorption_inverse=0.3,
            ),
            trading_allowed_thresholds=TradingAllowedThresholdsConfig(max_risk_score=0.96),
            validation=RiskValidationConfig(total_weight_min=0.5, total_weight_max=2.0),
        )

