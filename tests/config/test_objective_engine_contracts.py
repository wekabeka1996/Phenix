import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config.domains.objective_engine import (
    ObjectiveComponentConfig as DomainObjectiveComponentConfig,
    ObjectiveDataRequirementsConfig as DomainObjectiveDataRequirementsConfig,
    ObjectiveEngineDomainConfig as DomainObjectiveEngineDomainConfig,
    ObjectiveExplainabilityConfig as DomainObjectiveExplainabilityConfig,
    ObjectiveNormalizationConfig as DomainObjectiveNormalizationConfig,
)
from apps.reference.config_models import (
    ObjectiveComponentConfig,
    ObjectiveDataRequirementsConfig,
    ObjectiveEngineDomainConfig,
    ObjectiveExplainabilityConfig,
    ObjectiveNormalizationConfig,
)
from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchConfig,
    ObjectiveFeedbackConfig,
    ProviderConfig,
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


def test_current_aurora_config_loads_objective_engine_contract() -> None:
    cfg = ConfigLoader(Path("config/aurora")).load_config()

    assert cfg.domains.objective_engine.enabled is True
    assert "risk" in cfg.domains.objective_engine.components
    assert "max_position_qty" not in cfg.domains.objective_engine.components[
        "risk"].parameters
    assert cfg.strategies.aurora.objective.enabled is True
    assert cfg.strategies.md_amr.objective.enabled is True
    assert cfg.strategies.mean_reversion.objective.enabled is True
    assert cfg.strategies.mean_reversion.objective.regimes


def test_objective_engine_facade_reexports_are_exact_identity() -> None:
    assert ObjectiveNormalizationConfig is DomainObjectiveNormalizationConfig
    assert ObjectiveComponentConfig is DomainObjectiveComponentConfig
    assert ObjectiveDataRequirementsConfig is DomainObjectiveDataRequirementsConfig
    assert ObjectiveExplainabilityConfig is DomainObjectiveExplainabilityConfig
    assert ObjectiveEngineDomainConfig is DomainObjectiveEngineDomainConfig


def test_objective_engine_extraction_preserves_field_contract() -> None:
    _assert_field_contract(
        ObjectiveNormalizationConfig,
        required={
            "enabled",
            "method",
            "window_size",
            "min_samples",
            "target_range",
            "epsilon",
            "smoothing_factor",
            "outlier_threshold",
        },
        defaults={},
        default_factories={},
    )
    _assert_field_contract(
        ObjectiveComponentConfig,
        required={"enabled", "normalization", "parameters"},
        defaults={},
        default_factories={},
        optional_fields={"normalization"},
    )
    _assert_field_contract(
        ObjectiveDataRequirementsConfig,
        required={
            "require_arce",
            "require_portfolio",
            "require_execution",
            "strict_fail_closed",
        },
        defaults={},
        default_factories={},
    )
    _assert_field_contract(
        ObjectiveExplainabilityConfig,
        required={"enabled", "emit_subcomponents", "emit_normalization_stats"},
        defaults={},
        default_factories={},
    )
    _assert_field_contract(
        ObjectiveEngineDomainConfig,
        required={"enabled", "data_requirements",
                  "explainability", "components"},
        defaults={},
        default_factories={},
    )


def test_objective_engine_regime_coverage_negative_fixture_still_raises(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    registry_path = cfg_dir / "strategies.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["assignments"]["DOGEUSDT"] = ["mean_reversion"]
    registry["arbitration"]["priority"].setdefault("mean_reversion", 2)
    registry_path.write_text(
        yaml.safe_dump(registry, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    mr_path = cfg_dir / "strategies" / "mean_reversion.yaml"
    mr_wrapper = yaml.safe_load(mr_path.read_text(encoding="utf-8"))
    mr_config = mr_wrapper["mean_reversion"]

    assets = mr_config["assets"]
    objective_regimes = mr_config["objective"]["regimes"]
    expected_regimes: set[str] = set()
    for asset in assets.values():
        if not asset.get("enabled"):
            continue
        expected_regimes.update(
            str(regime).strip().upper()
            for regime in asset.get("allowed_regimes", [])
            if str(regime).strip()
        )

    removed_regime = next(
        regime for regime in sorted(expected_regimes) if regime in objective_regimes
    )
    objective_regimes.pop(removed_regime)
    mr_path.write_text(
        yaml.safe_dump(mr_wrapper, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    message = str(exc_info.value)
    assert "objective regime coverage invalid for assigned symbols" in message
    assert (
        f"mean_reversion:missing_objective_regimes={removed_regime}" in message
    )


def test_alpha_search_objective_feedback_requires_explicit_fields_when_enabled() -> None:
    with pytest.raises(ValidationError):
        AlphaSearchConfig(
            enabled=True,
            providers={
                "aurora": ProviderConfig(enabled=True),
            },
            objective_feedback=ObjectiveFeedbackConfig(enabled=True),
        )


def test_alpha_search_objective_feedback_window_contract() -> None:
    with pytest.raises(ValidationError):
        ObjectiveFeedbackConfig(
            enabled=True,
            window_trades=5,
            min_trades_before_reweight=6,
            rebalance_every_closed_trades=1,
            quality_metric_weights={"realized_quality_score": 1.0},
            min_provider_weight=0.1,
            max_provider_weight=0.5,
        )
