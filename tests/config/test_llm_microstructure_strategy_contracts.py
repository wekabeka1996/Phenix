from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.strategies.llm_microstructure as strategy_llm
import apps.reference.config_models as cm


CONFIG_DIR = Path("config/aurora")


CONTRACT_CASES = {
    "LLMMicrostructureStrategyConfig": {
        "required": {
            "mode",
            "enabled",
            "type",
            "description",
            "timeframe_sec",
            "pending_entry_ttl_ms",
            "execution",
            "safety_gates",
        },
        "defaults": {
            "allowed_sides": ["BUY", "SELL"],
            "decision": None,
            "objective": None,
        },
        "default_factories": {"allowed_regimes": list},
        "optional_fields": {"pending_entry_ttl_ms", "decision", "objective"},
    },
}


def _is_optional_union(tp: Any) -> bool:
    return type(None) in get_args(tp)


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


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def test_llm_microstructure_facade_reexports_are_exact_identity() -> None:
    assert cm.LLMMicrostructureStrategyConfig is strategy_llm.LLMMicrostructureStrategyConfig


def test_llm_microstructure_canonical_definition_lives_only_in_extracted_module() -> None:
    facade_source = Path(cm.__file__).read_text(encoding="utf-8")
    strategy_source = Path(strategy_llm.__file__).read_text(encoding="utf-8")

    marker = "\nclass LLMMicrostructureStrategyConfig("
    assert facade_source.count(marker) == 0, (
        "LLMMicrostructureStrategyConfig should no longer be defined in config_models.py after Pkg 3 extraction."
    )
    assert strategy_source.count(marker) == 1, (
        "LLMMicrostructureStrategyConfig must have exactly one top-level definition in apps.reference.config.strategies.llm_microstructure."
    )


def test_llm_microstructure_extraction_preserves_field_contract() -> None:
    for name, contract in CONTRACT_CASES.items():
        _assert_field_contract(
            getattr(cm, name),
            required=contract["required"],
            defaults=contract["defaults"],
            default_factories=contract["default_factories"],
            optional_fields=contract["optional_fields"],
        )


def test_llm_microstructure_extraction_preserves_cross_model_annotations() -> None:
    fields = cm.LLMMicrostructureStrategyConfig.model_fields

    assert fields["execution"].annotation is cm.StrategyExecutionConfig
    assert fields["safety_gates"].annotation is cm.SafetyGatesConfig
    assert _is_optional_union(fields["pending_entry_ttl_ms"].annotation)


def test_llm_microstructure_rebuild_seam_accepts_execution_block() -> None:
    cfg = cm.LLMMicrostructureStrategyConfig(
        mode="shadow",
        enabled=True,
        type="external_intent",
        description="contract test",
        timeframe_sec=60,
        pending_entry_ttl_ms=120000,
        execution={
            "entry_order_type": "LIMIT",
            "entry_tif": "GTC",
            "exit_order_type": "MARKET",
            "exit_tif": None,
            "exit_limit_ttl_ms": None,
            "gtx_retry_max": 0,
            "gtx_retry_offset_bps": 2.0,
        },
        safety_gates={
            "enabled": False,
            "system_stress_policy": "off",
            "stress_attenuation_factor": 0.5,
        },
    )

    assert type(cfg.execution) is cm.StrategyExecutionConfig
    assert type(cfg.safety_gates) is cm.SafetyGatesConfig
    assert cfg.pending_entry_ttl_ms == 120000


def test_current_aurora_config_loads_llm_microstructure_extraction_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    llm = cfg.strategies.llm_microstructure

    assert llm is not None
    assert type(llm) is cm.LLMMicrostructureStrategyConfig
    assert type(llm.execution) is cm.StrategyExecutionConfig
    assert type(llm.safety_gates) is cm.SafetyGatesConfig
    assert llm.type == "external_intent"
    assert llm.timeframe_sec == 60
    assert llm.pending_entry_ttl_ms == 120000
    assert llm.execution.entry_order_type == "LIMIT"
    assert llm.execution.entry_tif == "GTC"
    assert llm.safety_gates.enabled is False


def test_llm_microstructure_runtime_import_smoke() -> None:
    plugin_mod = importlib.import_module(
        "apps.reference.domains.strategies.plugins.llm_microstructure"
    )
    registry_mod = importlib.import_module(
        "apps.reference.domains.strategies.registry"
    )
    bridge_mod = importlib.import_module(
        "apps.reference.domains.shadow_telemetry.main_bridge"
    )
    intent_router_mod = importlib.import_module(
        "apps.reference.domains.execution_position.flows.open.intent_router"
    )

    assert hasattr(plugin_mod, "LlmMicrostructurePlugin")
    assert hasattr(registry_mod, "StrategyRuntime")
    assert hasattr(bridge_mod, "LLMIntentIngressBridge")
    assert hasattr(bridge_mod, "register_llm_command_mapper")
    assert hasattr(intent_router_mod, "IntentRouter")


def test_llm_microstructure_yaml_contract_fails_closed_on_invalid_pending_entry_ttl(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    llm_path = cfg_dir / "strategies" / "llm_microstructure.yaml"
    llm_data = yaml.safe_load(llm_path.read_text(encoding="utf-8"))
    llm_data["llm_microstructure"]["pending_entry_ttl_ms"] = 999
    _write_yaml(llm_path, llm_data)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "pending_entry_ttl_ms" in message
    assert "1000" in message


def test_llm_microstructure_yaml_contract_fails_closed_on_forbidden_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    llm_path = cfg_dir / "strategies" / "llm_microstructure.yaml"
    llm_data = yaml.safe_load(llm_path.read_text(encoding="utf-8"))
    llm_data["llm_microstructure"]["unexpected_pkg3_field"] = True
    _write_yaml(llm_path, llm_data)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg3_field" in message
    assert "extra inputs are not permitted" in message.lower()
