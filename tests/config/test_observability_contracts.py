from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml

from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import ConfigLoader
import apps.reference.config.system.observability as system_observability
import apps.reference.config_models as cm
from apps.reference.telemetry.shadow_journal import DEFAULT_CRITICAL_EVENTS


CONFIG_DIR = Path("config/aurora")
MOVED_SURFACE = (
    "LogRotationConfig",
    "ConsoleLogConfig",
    "CoreLogSinkConfig",
    "DomainLogConfig",
    "EventChainLogConfig",
    "ObservabilityLoggingConfig",
    "AlertsConfig",
    "ShadowCriticalEventJournalConfig",
    "ObservabilityConfig",
)


def _is_optional_union(tp: Any) -> bool:
    return type(None) in get_args(tp)


def _annotation_includes(tp: Any, expected: Any) -> bool:
    return tp is expected or expected in get_args(tp)


def _assert_field_contract(
    model_cls: type,
    *,
    required: set[str],
    defaults: dict[str, Any],
    factory_fields: dict[str, Any],
    dynamic_factories: dict[str, Any],
    optional_fields: set[str] | None = None,
) -> None:
    optional_fields = optional_fields or set()
    fields = model_cls.model_fields
    expected_fields = (
        required
        | set(defaults)
        | set(factory_fields)
        | set(dynamic_factories)
    )

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

    for name, expected_factory in factory_fields.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay default-factory backed"
        )
        assert field_info.default_factory is expected_factory

    for name, expected_output in dynamic_factories.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay default-factory backed"
        )
        assert field_info.default_factory is not None
        first_default = field_info.get_default(call_default_factory=True)
        second_default = field_info.get_default(call_default_factory=True)
        assert first_default == expected_output
        assert second_default == expected_output
        assert first_default is not second_default

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


def test_observability_facade_reexports_are_exact_identity() -> None:
    for name in MOVED_SURFACE:
        assert getattr(cm, name) is getattr(system_observability, name)


def test_observability_canonical_definitions_live_only_in_extracted_module() -> None:
    facade_source = Path(cm.__file__).read_text(encoding="utf-8")
    module_source = Path(
        system_observability.__file__).read_text(encoding="utf-8")

    for name in MOVED_SURFACE:
        marker = f"\nclass {name}("
        assert facade_source.count(marker) == 0, (
            f"{name} should no longer be defined in config_models.py after Pkg 1 extraction."
        )
        assert module_source.count(marker) == 1, (
            f"{name} must have exactly one top-level definition in apps.reference.config.system.observability."
        )


def test_observability_extraction_preserves_field_contract() -> None:
    _assert_field_contract(
        cm.LogRotationConfig,
        required={"max_bytes", "backup_count"},
        defaults={},
        factory_fields={},
        dynamic_factories={},
    )
    _assert_field_contract(
        cm.ConsoleLogConfig,
        required={"enabled", "level", "format", "colorize"},
        defaults={},
        factory_fields={},
        dynamic_factories={},
    )
    _assert_field_contract(
        cm.CoreLogSinkConfig,
        required={"enabled", "path", "level",
                  "format", "max_bytes", "backup_count"},
        defaults={},
        factory_fields={},
        dynamic_factories={},
        optional_fields={"max_bytes", "backup_count"},
    )
    _assert_field_contract(
        cm.DomainLogConfig,
        required={"enabled", "level", "max_bytes", "backup_count"},
        defaults={},
        factory_fields={},
        dynamic_factories={},
    )
    _assert_field_contract(
        cm.EventChainLogConfig,
        required={"enabled", "path", "level",
                  "format", "max_bytes", "backup_count"},
        defaults={},
        factory_fields={},
        dynamic_factories={},
    )
    _assert_field_contract(
        cm.ObservabilityLoggingConfig,
        required={
            "default_level",
            "default_format",
            "rotation",
            "console",
            "core",
            "domains",
            "event_chain",
        },
        defaults={},
        factory_fields={},
        dynamic_factories={},
    )
    _assert_field_contract(
        cm.AlertsConfig,
        required={
            "slack_webhook_url",
            "deduplication_window_sec",
            "max_alerts_per_hour",
            "risk_gate_threshold_pct",
            "wal_size_threshold_mb",
            "cb_active_threshold_sec",
            "recent_alerts_max_keys",
            "entropy_volume_threshold",
            "entropy_error_rate_threshold",
            "check_interval_sec",
        },
        defaults={},
        factory_fields={},
        dynamic_factories={},
        optional_fields={"slack_webhook_url"},
    )
    _assert_field_contract(
        cm.ShadowCriticalEventJournalConfig,
        required={"enabled", "path", "schema_version",
                  "instrumentation_version", "critical_events"},
        defaults={},
        factory_fields={},
        dynamic_factories={},
    )
    _assert_field_contract(
        cm.ObservabilityConfig,
        required={"config_version", "logging", "alerts", "shadow_journal"},
        defaults={},
        factory_fields={},
        dynamic_factories={},
    )


def test_observability_extraction_preserves_cross_model_annotations() -> None:
    logging_fields = cm.ObservabilityLoggingConfig.model_fields
    assert logging_fields["rotation"].annotation is cm.LogRotationConfig
    assert logging_fields["console"].annotation is cm.ConsoleLogConfig
    assert logging_fields["core"].annotation is cm.CoreLogSinkConfig
    assert _annotation_includes(
        logging_fields["domains"].annotation, cm.DomainLogConfig)
    assert logging_fields["event_chain"].annotation is cm.EventChainLogConfig

    observability_fields = cm.ObservabilityConfig.model_fields
    assert observability_fields["logging"].annotation is cm.ObservabilityLoggingConfig
    assert observability_fields["alerts"].annotation is cm.AlertsConfig
    assert observability_fields["shadow_journal"].annotation is cm.ShadowCriticalEventJournalConfig


def test_current_aurora_config_loads_observability_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    observability = cfg.observability

    assert type(observability) is cm.ObservabilityConfig
    assert observability.config_version == "1.0.0"

    logging_cfg = observability.logging
    assert type(logging_cfg) is cm.ObservabilityLoggingConfig
    assert logging_cfg.default_level == "INFO"
    assert logging_cfg.default_format == "text"
    assert type(logging_cfg.rotation) is cm.LogRotationConfig
    assert logging_cfg.rotation.max_bytes == 10485760
    assert logging_cfg.rotation.backup_count == 50
    assert type(logging_cfg.console) is cm.ConsoleLogConfig
    assert logging_cfg.console.enabled is True
    assert logging_cfg.console.level == "INFO"
    assert logging_cfg.console.format == "text"
    assert type(logging_cfg.core) is cm.CoreLogSinkConfig
    assert logging_cfg.core.enabled is True
    assert logging_cfg.core.path == "logs/aurora_core.log"
    assert logging_cfg.core.level == "DEBUG"
    assert logging_cfg.core.max_bytes == 10485760
    assert logging_cfg.core.backup_count == 50
    assert set(logging_cfg.domains) == {
        "feature_engineering",
        "risk_management",
        "decision_making",
        "execution_position",
        "regime_detector",
        "mean_reversion",
    }
    assert all(type(domain_cfg)
               is cm.DomainLogConfig for domain_cfg in logging_cfg.domains.values())
    assert logging_cfg.domains["execution_position"].backup_count == 30
    assert logging_cfg.domains["mean_reversion"].max_bytes == 5242880
    assert type(logging_cfg.event_chain) is cm.EventChainLogConfig
    assert logging_cfg.event_chain.path == "logs/event_chain.log"
    assert logging_cfg.event_chain.format == "json"
    assert logging_cfg.event_chain.backup_count == 50

    assert type(observability.alerts) is cm.AlertsConfig
    assert observability.alerts.slack_webhook_url is None
    assert observability.alerts.max_alerts_per_hour == 10
    assert observability.alerts.entropy_volume_threshold == 3000

    assert type(
        observability.shadow_journal) is cm.ShadowCriticalEventJournalConfig
    assert observability.shadow_journal.enabled is True
    assert observability.shadow_journal.path == "logs/shadow_critical_event_journal_v1.jsonl"
    assert observability.shadow_journal.schema_version == "1.0.0"
    assert observability.shadow_journal.instrumentation_version == "1.0.0"
    assert "EVT:NEOCORTEX_AUTHORITY_SEAM_DECISION" in observability.shadow_journal.critical_events
    assert "EVT:TRADE_INTENT_PROPOSED" in observability.shadow_journal.critical_events
    assert "CACHE:EXECUTION_TERMINAL_IDENTITY_CACHE_LOAD_FAILED" in observability.shadow_journal.critical_events
    assert "EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE" in observability.shadow_journal.critical_events


def test_observability_runtime_import_smoke() -> None:
    modules = {
        name: importlib.import_module(name)
        for name in (
            "apps.reference.config_models",
            "apps.reference.config.system.observability",
            "apps.reference.config_loader",
            "apps.reference.logging_setup",
            "apps.reference.telemetry.alerts",
            "apps.reference.telemetry.shadow_journal",
        )
    }

    assert hasattr(modules["apps.reference.logging_setup"], "setup_logging")
    assert hasattr(modules["apps.reference.telemetry.alerts"], "AlertManager")
    assert hasattr(
        modules["apps.reference.telemetry.shadow_journal"], "DEFAULT_CRITICAL_EVENTS")


def test_observability_yaml_contract_fails_closed_on_forbidden_root_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    observability_path = cfg_dir / "observability.yaml"
    payload = _load_yaml(observability_path)
    payload["unexpected_pkg1_observability_field"] = True
    _write_yaml(observability_path, payload)

    with pytest.raises(ConfigContractError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "Path='observability'" in message
    assert "unexpected_pkg1_observability_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_observability_yaml_contract_fails_closed_on_invalid_console_level(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    observability_path = cfg_dir / "observability.yaml"
    payload = _load_yaml(observability_path)
    payload["logging"]["console"]["level"] = "TRACE"
    _write_yaml(observability_path, payload)

    with pytest.raises(ConfigContractError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "Path='observability'" in message
    assert "TRACE" in message
    assert "logging.console.level" in message


def test_observability_yaml_contract_fails_closed_on_forbidden_shadow_journal_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    observability_path = cfg_dir / "observability.yaml"
    payload = _load_yaml(observability_path)
    payload["shadow_journal"]["unexpected_pkg1_shadow_field"] = True
    _write_yaml(observability_path, payload)

    with pytest.raises(ConfigContractError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "Path='observability'" in message
    assert "unexpected_pkg1_shadow_field" in message
    assert "extra inputs are not permitted" in message.lower()
