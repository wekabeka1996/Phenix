from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.domains._aggregator as domain_agg
import apps.reference.config_models as cm


CONFIG_DIR = Path("config/aurora")


def _is_optional_union(tp: Any) -> bool:
    return type(None) in get_args(tp)


def _assert_field_contract(
    model_cls: type,
    *,
    required: set[str],
    defaults: dict[str, Any],
    class_factories: dict[str, Any],
    optional_fields: set[str] | None = None,
) -> None:
    optional_fields = optional_fields or set()
    fields = model_cls.model_fields
    expected_fields = required | set(defaults) | set(class_factories)

    assert set(fields) == expected_fields
    assert model_cls.model_config.get("extra") == "forbid"

    for name in required:
        field_info = fields[name]
        assert field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay required"
        )
        assert field_info.default_factory is None

    for name, expected_default in defaults.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay optional/defaulted"
        )
        assert field_info.default == expected_default
        assert field_info.default_factory is None

    for name, expected_factory in class_factories.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay default-factory backed"
        )
        assert field_info.default_factory is expected_factory

    for name in optional_fields:
        assert _is_optional_union(fields[name].annotation), (
            f"{model_cls.__name__}.{name} must stay Optional in the extraction contract"
        )


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def test_aggregator_facade_reexports_are_exact_identity() -> None:
    assert cm.DomainsDebugConfig is domain_agg.DomainsDebugConfig
    assert cm.DomainsConfig is domain_agg.DomainsConfig


def test_aggregator_canonical_definitions_live_only_in_extracted_module() -> None:
    facade_source = Path(cm.__file__).read_text(encoding="utf-8")
    domain_source = Path(domain_agg.__file__).read_text(encoding="utf-8")

    for name in ("DomainsDebugConfig", "DomainsConfig"):
        marker = f"\nclass {name}("
        assert facade_source.count(marker) == 0, (
            f"{name} should no longer be defined in config_models.py after Pkg 9 extraction."
        )
        assert domain_source.count(marker) == 1, (
            f"{name} must have exactly one top-level definition in apps.reference.config.domains._aggregator."
        )


def test_aggregator_extraction_preserves_field_contract() -> None:
    _assert_field_contract(
        cm.DomainsDebugConfig,
        required={"disable_positions_stale_gate", "disable_daily_loss_limit"},
        defaults={},
        class_factories={},
    )
    _assert_field_contract(
        cm.DomainsConfig,
        required={
            "debug",
            "decision_making",
            "feature_engineering",
            "ta_features",
            "risk_management",
            "position_tracking",
            "execution_position",
            "shadow_telemetry",
            "objective_engine",
        },
        defaults={},
        class_factories={},
        optional_fields={"ta_features"},
    )

    fields = cm.DomainsConfig.model_fields
    assert fields["debug"].annotation is cm.DomainsDebugConfig
    assert fields["decision_making"].annotation is cm.DecisionMakingDomainConfig
    assert fields["feature_engineering"].annotation is cm.FeatureEngineeringDomainConfig
    assert _is_optional_union(fields["ta_features"].annotation)
    assert fields["risk_management"].annotation is cm.RiskManagementDomainConfig
    assert fields["position_tracking"].annotation is cm.PositionTrackingDomainConfig
    assert fields["execution_position"].annotation is cm.ExecutionPositionDomainConfig
    assert fields["shadow_telemetry"].annotation is cm.ShadowTelemetryDomainConfig
    assert fields["objective_engine"].annotation is cm.ObjectiveEngineDomainConfig


def test_current_aurora_config_loads_aggregator_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    assert type(cfg.domains) is cm.DomainsConfig
    assert type(cfg.domains.debug) is cm.DomainsDebugConfig
    assert cfg.domains.debug.disable_positions_stale_gate is False
    assert cfg.domains.debug.disable_daily_loss_limit is False
    assert type(cfg.domains.decision_making) is cm.DecisionMakingDomainConfig
    assert type(
        cfg.domains.feature_engineering) is cm.FeatureEngineeringDomainConfig
    assert type(cfg.domains.ta_features) is cm.TAFeaturesDomainConfig
    assert type(cfg.domains.risk_management) is cm.RiskManagementDomainConfig
    assert type(cfg.domains.position_tracking) is cm.PositionTrackingDomainConfig
    assert type(
        cfg.domains.execution_position) is cm.ExecutionPositionDomainConfig
    assert type(cfg.domains.shadow_telemetry) is cm.ShadowTelemetryDomainConfig
    assert type(cfg.domains.objective_engine) is cm.ObjectiveEngineDomainConfig


def test_aggregator_yaml_contract_fails_closed_on_forbidden_debug_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["debug"]["unexpected_pkg9_debug_field"] = True
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg9_debug_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_aggregator_yaml_contract_fails_closed_on_forbidden_domains_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["unexpected_pkg9_domains_field"] = {}
    _write_yaml(domains_path, domains)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg9_domains_field" in message
    assert "extra inputs are not permitted" in message.lower()
