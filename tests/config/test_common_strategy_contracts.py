from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.strategies.common as strategy_common
import apps.reference.config_models as cm


CONFIG_DIR = Path("config/aurora")
MOVED_SURFACE = (
    "StrategiesArbitrationLoggingConfig",
    "StrategiesArbitrationConfig",
    "StrategiesRegistryConfig",
    "StrategyObjectiveMultiplierConfig",
    "StrategyObjectiveGateConfig",
    "StrategyObjectiveRegimeProfile",
    "StrategyObjectiveConfig",
    "StrategiesConfig",
)

CONTRACT_CASES = {
    "StrategiesArbitrationLoggingConfig": {
        "required": {"rejected_why_prefix", "log_level"},
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "StrategiesArbitrationConfig": {
        "required": {"mode", "window_ms", "priority", "logging"},
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "StrategiesRegistryConfig": {
        "required": {"version", "assignments", "arbitration"},
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "StrategyObjectiveMultiplierConfig": {
        "required": {
            "m_min",
            "m_max",
            "lambda_scale",
            "penalty_center",
            "penalty_scale",
        },
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "StrategyObjectiveGateConfig": {
        "required": {"min_objective_score", "enforcement_mode"},
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "StrategyObjectiveRegimeProfile": {
        "required": {"weights", "multiplier", "gate"},
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "StrategyObjectiveConfig": {
        "required": {"enabled", "regimes"},
        "defaults": {},
        "default_factories": {},
        "optional_fields": set(),
    },
    "StrategiesConfig": {
        "required": {
            "aurora",
            "mean_reversion",
            "alpha_mr_s01",
            "md_amr",
            "llm_microstructure",
            "alpha_ta_ensemble",
        },
        "defaults": {},
        "default_factories": {},
        "optional_fields": {
            "aurora",
            "mean_reversion",
            "alpha_mr_s01",
            "md_amr",
            "llm_microstructure",
            "alpha_ta_ensemble",
        },
    },
}


def _is_optional_union(tp: Any) -> bool:
    return type(None) in get_args(tp)


def _annotation_includes(tp: Any, expected: Any) -> bool:
    return tp is expected or expected in get_args(tp)


def _assert_field_contract(
    model_cls: type,
    *,
    required: set[str],
    defaults: dict[str, Any],
    default_factories: dict[str, Any],
    optional_fields: set[str],
) -> None:
    fields = model_cls.model_fields
    expected_fields = required | set(defaults) | set(default_factories)

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

    for name, expected_factory in default_factories.items():
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


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def test_common_facade_reexports_are_exact_identity() -> None:
    for name in MOVED_SURFACE:
        assert getattr(cm, name) is getattr(strategy_common, name)


def test_common_module_owns_moved_surface_once() -> None:
    facade_source = Path(cm.__file__).read_text(encoding="utf-8")
    common_source = Path(strategy_common.__file__).read_text(encoding="utf-8")

    for name in MOVED_SURFACE:
        marker = f"\nclass {name}("
        assert facade_source.count(marker) == 0, (
            f"{name} should no longer be defined in config_models.py"
        )
        assert common_source.count(marker) == 1, (
            f"{name} must have exactly one canonical definition in common.py"
        )


def test_common_extraction_preserves_field_contract() -> None:
    for name, contract in CONTRACT_CASES.items():
        _assert_field_contract(getattr(cm, name), **contract)


def test_common_annotation_and_rebuild_contracts_hold() -> None:
    registry_fields = cm.StrategiesRegistryConfig.model_fields
    arbitration_fields = cm.StrategiesArbitrationConfig.model_fields
    profile_fields = cm.StrategyObjectiveRegimeProfile.model_fields
    strategies_fields = cm.StrategiesConfig.model_fields
    common_strategies_fields = strategy_common.StrategiesConfig.model_fields

    assert registry_fields["arbitration"].annotation is cm.StrategiesArbitrationConfig
    assert arbitration_fields["logging"].annotation is cm.StrategiesArbitrationLoggingConfig
    assert profile_fields["multiplier"].annotation is cm.StrategyObjectiveMultiplierConfig
    assert profile_fields["gate"].annotation is cm.StrategyObjectiveGateConfig

    assert _annotation_includes(
        cm.AuroraStrategyConfig.model_fields["objective"].annotation,
        cm.StrategyObjectiveConfig,
    )
    assert _annotation_includes(
        cm.MeanReversion1mStrategyConfig.model_fields["objective"].annotation,
        cm.StrategyObjectiveConfig,
    )
    assert _annotation_includes(
        cm.MDAMRStrategyConfig.model_fields["objective"].annotation,
        cm.StrategyObjectiveConfig,
    )

    assert _annotation_includes(
        strategies_fields["aurora"].annotation,
        cm.AuroraStrategyConfig,
    )
    assert _annotation_includes(
        strategies_fields["mean_reversion"].annotation,
        cm.MeanReversion1mStrategyConfig,
    )
    assert _annotation_includes(
        strategies_fields["alpha_mr_s01"].annotation,
        cm.AlphaMrS01StrategyConfig,
    )
    assert _annotation_includes(
        strategies_fields["md_amr"].annotation,
        cm.MDAMRStrategyConfig,
    )
    assert _annotation_includes(
        strategies_fields["llm_microstructure"].annotation,
        cm.LLMMicrostructureStrategyConfig,
    )
    assert _annotation_includes(
        strategies_fields["alpha_ta_ensemble"].annotation,
        cm.AlphaTaEnsembleStrategyConfig,
    )

    assert _annotation_includes(
        common_strategies_fields["aurora"].annotation,
        cm.AuroraStrategyConfig,
    )
    assert _annotation_includes(
        common_strategies_fields["mean_reversion"].annotation,
        cm.MeanReversion1mStrategyConfig,
    )
    assert _annotation_includes(
        common_strategies_fields["alpha_mr_s01"].annotation,
        cm.AlphaMrS01StrategyConfig,
    )
    assert _annotation_includes(
        common_strategies_fields["md_amr"].annotation,
        cm.MDAMRStrategyConfig,
    )
    assert _annotation_includes(
        common_strategies_fields["llm_microstructure"].annotation,
        cm.LLMMicrostructureStrategyConfig,
    )
    assert _annotation_includes(
        common_strategies_fields["alpha_ta_ensemble"].annotation,
        cm.AlphaTaEnsembleStrategyConfig,
    )


def test_current_aurora_config_loads_common_surface() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    assert type(cfg.strategies_registry) is cm.StrategiesRegistryConfig
    assert type(
        cfg.strategies_registry.arbitration) is cm.StrategiesArbitrationConfig
    assert (
        type(cfg.strategies_registry.arbitration.logging)
        is cm.StrategiesArbitrationLoggingConfig
    )
    assert type(cfg.strategies) is cm.StrategiesConfig

    assert cfg.strategies.aurora is not None
    assert cfg.strategies.aurora.objective is not None
    assert type(cfg.strategies.aurora.objective) is cm.StrategyObjectiveConfig

    assert cfg.strategies.mean_reversion is not None
    assert cfg.strategies.mean_reversion.objective is not None
    assert type(
        cfg.strategies.mean_reversion.objective) is cm.StrategyObjectiveConfig

    assert cfg.strategies.md_amr is not None
    assert cfg.strategies.md_amr.objective is not None
    assert type(cfg.strategies.md_amr.objective) is cm.StrategyObjectiveConfig

    assert cfg.strategies.llm_microstructure is not None
    assert type(
        cfg.strategies.llm_microstructure) is cm.LLMMicrostructureStrategyConfig


def test_runtime_consumers_bind_common_surface_types() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    modules = {
        name: importlib.import_module(name)
        for name in (
            "apps.reference.config_models",
            "apps.reference.config.strategies.common",
            "apps.reference.config_loader",
            "apps.reference.domain_config",
            "apps.reference.domains.strategies.registry",
            "apps.reference.domains.objective_engine.engine",
            "apps.reference.domains.objective_engine.pretrade_kernel",
            "apps.reference.config.strategies.aurora",
            "apps.reference.config.strategies.mean_reversion",
            "apps.reference.config.strategies.md_amr",
            "apps.reference.config.strategies.llm_microstructure",
        )
    }

    resolver = modules[
        "apps.reference.domain_config"
    ].DomainConfigResolver(cfg)
    assert type(resolver.get_strategies_registry()
                ) is cm.StrategiesRegistryConfig

    engine_mod = modules["apps.reference.domains.objective_engine.engine"]
    pretrade_mod = modules[
        "apps.reference.domains.objective_engine.pretrade_kernel"
    ]
    registry_mod = modules["apps.reference.domains.strategies.registry"]

    assert engine_mod.StrategyObjectiveConfig is cm.StrategyObjectiveConfig
    assert pretrade_mod.StrategyObjectiveConfig is cm.StrategyObjectiveConfig
    assert hasattr(registry_mod, "StrategyRuntime")


def test_strategy_objective_multiplier_rejects_inverted_range() -> None:
    with pytest.raises(ValidationError):
        cm.StrategyObjectiveMultiplierConfig(
            m_min=0.9,
            m_max=0.8,
            lambda_scale=1.0,
            penalty_center=0.0,
            penalty_scale=1.0,
        )


def test_strategy_objective_requires_regimes_when_enabled() -> None:
    with pytest.raises(ValidationError):
        cm.StrategyObjectiveConfig(enabled=True)


def test_strategies_registry_missing_priority_for_hybrid_symbol_still_fails() -> None:
    with pytest.raises(ValidationError) as exc_info:
        cm.StrategiesRegistryConfig(
            version="1.0.0",
            assignments={"BTCUSDT": ["aurora", "mean_reversion"]},
            arbitration=cm.StrategiesArbitrationConfig(
                mode="priority",
                window_ms=1000,
                priority={"aurora": 1},
                logging=cm.StrategiesArbitrationLoggingConfig(
                    rejected_why_prefix="ARBITRATION_REJECT",
                    log_level="INFO",
                ),
            ),
        )

    assert "missing_priority" in str(exc_info.value)


def test_mean_reversion_root_assignment_validator_still_fails_closed(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    registry_path = cfg_dir / "strategies.yaml"
    registry_payload = _load_yaml(registry_path)
    registry_payload["assignments"]["DOGEUSDT"] = ["mean_reversion"]
    _write_yaml(registry_path, registry_payload)

    mr_path = cfg_dir / "strategies" / "mean_reversion.yaml"
    mr_payload = _load_yaml(mr_path)
    mr_payload["mean_reversion"]["enabled"] = False
    _write_yaml(mr_path, mr_payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "mean_reversion enabled=false for assigned symbols" in str(
        exc_info.value
    )


def test_md_amr_root_assignment_validator_still_fails_closed(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    md_path = cfg_dir / "strategies" / "md_amr.yaml"
    md_payload = _load_yaml(md_path)
    md_payload["md_amr"]["enabled"] = False
    _write_yaml(md_path, md_payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    assert "md_amr enabled=false for assigned symbols" in str(exc_info.value)
