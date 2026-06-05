import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config.domains.risk_management import (
    RiskManagementDomainConfig as DomainRiskManagementDomainConfig,
    RiskScoreWeightsConfig as DomainRiskScoreWeightsConfig,
    RiskValidationConfig as DomainRiskValidationConfig,
    TradingAllowedThresholdsConfig as DomainTradingAllowedThresholdsConfig,
)
from apps.reference.config_models import (
    RiskManagementDomainConfig,
    RiskScoreWeightsConfig,
    RiskValidationConfig,
    TradingAllowedThresholdsConfig,
)


CONFIG_DIR = Path("config/aurora")


def _is_optional_union(tp: Any) -> bool:
    return type(None) in get_args(tp)


def _assert_field_contract(
    model_cls: type,
    *,
    required: set[str],
    defaults: dict[str, Any],
    default_factories: dict[str, Any],
    optional_fields: set[str] | None = None,
) -> None:
    optional_fields = optional_fields or set()
    fields = model_cls.model_fields
    expected_fields = required | set(defaults) | set(default_factories)

    assert set(fields) == expected_fields
    assert model_cls.model_config.get("extra") == "forbid"

    for name in required:
        field_info = fields[name]
        assert field_info.is_required(
        ), f"{model_cls.__name__}.{name} must stay required"
        assert field_info.default_factory is None

    for name, expected_default in defaults.items():
        field_info = fields[name]
        assert not field_info.is_required(
        ), f"{model_cls.__name__}.{name} must stay optional/defaulted"
        assert field_info.default == expected_default
        assert field_info.default_factory is None

    for name, expected_factory in default_factories.items():
        field_info = fields[name]
        assert not field_info.is_required(
        ), f"{model_cls.__name__}.{name} must stay default-factory backed"
        assert field_info.default_factory is expected_factory

    for name in optional_fields:
        assert _is_optional_union(fields[name].annotation), (
            f"{model_cls.__name__}.{name} must stay Optional in the extraction contract"
        )


def test_current_aurora_config_loads_risk_management_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    rm = cfg.domains.risk_management
    assert rm.use_absorption_penalty is True
    assert rm.absorption_dp_cap_pct == pytest.approx(0.02)
    assert rm.absorption_penalty_source == "feature"
    assert rm.risk_score_weights.absorption_feature == pytest.approx(0.2)
    assert rm.trading_allowed_thresholds.max_risk_score == pytest.approx(0.96)
    assert rm.validation.total_weight_min == pytest.approx(0.5)
    assert rm.validation.total_weight_max == pytest.approx(2.0)


def test_risk_management_facade_reexports_are_exact_identity() -> None:
    assert RiskScoreWeightsConfig is DomainRiskScoreWeightsConfig
    assert TradingAllowedThresholdsConfig is DomainTradingAllowedThresholdsConfig
    assert RiskValidationConfig is DomainRiskValidationConfig
    assert RiskManagementDomainConfig is DomainRiskManagementDomainConfig


def test_risk_management_extraction_preserves_field_contract() -> None:
    _assert_field_contract(
        RiskScoreWeightsConfig,
        required={"delta_price_pct", "obi", "tfi",
                  "absorption_inverse", "absorption_feature"},
        defaults={},
        default_factories={},
    )
    _assert_field_contract(
        TradingAllowedThresholdsConfig,
        required={"max_risk_score"},
        defaults={},
        default_factories={},
    )
    _assert_field_contract(
        RiskValidationConfig,
        required={"total_weight_min", "total_weight_max"},
        defaults={},
        default_factories={},
    )
    _assert_field_contract(
        RiskManagementDomainConfig,
        required={
            "risk_score_weights",
            "trading_allowed_thresholds",
            "validation",
            "use_absorption_penalty",
            "absorption_dp_cap_pct",
            "absorption_penalty_source",
            "absorption_feature_clip_min",
            "absorption_feature_clip_max",
        },
        defaults={},
        default_factories={},
        optional_fields={"absorption_dp_cap_pct"},
    )


def test_risk_management_yaml_contract_fails_closed_without_dp_cap(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["risk_management"].pop("absorption_dp_cap_pct", None)
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    message = str(exc_info.value)
    assert "absorption_dp_cap_pct" in message
    assert "field required" in message.lower()
