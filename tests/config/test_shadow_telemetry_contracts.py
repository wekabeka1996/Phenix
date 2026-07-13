import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config.domains.shadow_telemetry import (
    AgentAuthorityPolicyConfig,
    ShadowTelemetryApiConfig as DomainShadowTelemetryApiConfig,
    ShadowTelemetryReadModelConfig as DomainShadowTelemetryReadModelConfig,
    ShadowTelemetryApiWriteConfig as DomainShadowTelemetryApiWriteConfig,
    ShadowTelemetryDomainConfig as DomainShadowTelemetryDomainConfig,
    ShadowTelemetryEgressToMainConfig as DomainShadowTelemetryEgressToMainConfig,
    ShadowTelemetryIngestConfig as DomainShadowTelemetryIngestConfig,
    ShadowTelemetryLedgerConfig as DomainShadowTelemetryLedgerConfig,
    ShadowTelemetryLifecycleConfig as DomainShadowTelemetryLifecycleConfig,
    ShadowTelemetrySnapshotConfig as DomainShadowTelemetrySnapshotConfig,
    ShadowTelemetryTfPolicyConfig as DomainShadowTelemetryTfPolicyConfig,
)
from apps.reference.config_models import (
    ShadowTelemetryApiConfig,
    ShadowTelemetryReadModelConfig,
    ShadowTelemetryApiWriteConfig,
    ShadowTelemetryDomainConfig,
    ShadowTelemetryEgressToMainConfig,
    ShadowTelemetryIngestConfig,
    ShadowTelemetryLedgerConfig,
    ShadowTelemetryLifecycleConfig,
    ShadowTelemetrySnapshotConfig,
    ShadowTelemetryTfPolicyConfig,
)


CONFIG_DIR = Path("config/aurora")


def _assert_field_contract(
    model_cls: type,
    *,
    required: set[str],
    defaults: dict[str, Any],
    class_factories: dict[str, Any],
    dynamic_factories: dict[str, Any],
) -> None:
    fields = model_cls.model_fields
    expected_fields = (
        required
        | set(defaults)
        | set(class_factories)
        | set(dynamic_factories)
    )

    assert set(fields) == expected_fields
    assert model_cls.model_config.get("extra") == "forbid"

    for name in required:
        field_info = fields[name]
        assert field_info.is_required(
        ), f"{model_cls.__name__}.{name} must stay required"
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


def test_current_aurora_config_loads_shadow_telemetry_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    st = cfg.domains.shadow_telemetry
    assert st.enabled is True
    assert st.required_for_mode is False
    assert st.ingest.source == "ipc_tap"
    assert st.ingest.ipc_endpoint == "tcp://127.0.0.1:7101"
    assert "EVT:LLM_INTENT_RECEIVED_V1" in st.ingest.allowlist_events
    assert st.api.enabled is True
    assert st.api.host == "127.0.0.1"
    assert st.api.port == 8443
    assert st.api.tls is False
    assert st.api.auth_mode == "loopback_optional_bearer"
    assert st.api.write.symbol_allowlist == [
        "DOGEUSDT",
        "BTCUSDT",
        "ETHUSDT",
        "XRPUSDT",
        "BNBUSDT",
        "SOLUSDT",
    ]
    assert st.api.write.require_snapshot_ref is True
    assert st.egress_to_main.mode == "ipc"
    assert st.egress_to_main.ipc_commands_endpoint == "tcp://127.0.0.1:7102"
    assert st.ledger.queue_maxsize == 50000
    assert st.ledger.overflow_policy == "fail_closed"
    assert st.ledger.enqueue_timeout_ms == 5
    assert st.ledger.shutdown_timeout_ms == 2000
    assert st.lifecycle.stop_timeout_ms == 2000
    assert st.agent_authority.config_version == "p46-1e-v1"
    assert st.agent_authority.execution_capable_participant_types == ["MAIN_AGENT"]
    assert st.snapshot.trigger_event == "EVT:FEATURES_CALCULATED"
    assert st.snapshot.tf_policy.tick_snapshots_mode == "sampled"
    assert st.snapshot.tf_policy.tick_sample_every_n == 20
    assert st.snapshot.tf_policy.min_tf_sec_for_full == 60
    assert st.snapshot.output_dir == "data/shadow_telemetry/snapshots"


def test_shadow_telemetry_facade_reexports_are_exact_identity() -> None:
    assert ShadowTelemetryIngestConfig is DomainShadowTelemetryIngestConfig
    assert ShadowTelemetryApiWriteConfig is DomainShadowTelemetryApiWriteConfig
    assert ShadowTelemetryApiConfig is DomainShadowTelemetryApiConfig
    assert ShadowTelemetryEgressToMainConfig is DomainShadowTelemetryEgressToMainConfig
    assert ShadowTelemetryTfPolicyConfig is DomainShadowTelemetryTfPolicyConfig
    assert ShadowTelemetryLedgerConfig is DomainShadowTelemetryLedgerConfig
    assert ShadowTelemetryLifecycleConfig is DomainShadowTelemetryLifecycleConfig
    assert ShadowTelemetrySnapshotConfig is DomainShadowTelemetrySnapshotConfig
    assert ShadowTelemetryDomainConfig is DomainShadowTelemetryDomainConfig


def test_shadow_telemetry_extraction_preserves_field_contract() -> None:
    _assert_field_contract(
        AgentAuthorityPolicyConfig,
        required={
            "config_version", "supported_session_statuses", "allowed_participant_types",
            "execution_capable_participant_types", "lease_ttl_sec",
            "renewal_requires_owner", "expiry_behavior", "conflict_behavior",
            "session_instrument_universe", "max_position_horizon_sec", "intent_ttl_sec",
            "account_snapshot_max_age_sec", "market_snapshot_max_age_sec",
            "execution_order_type", "execution_time_in_force", "execution_valid_for_ms",
            "context_ack_policy",
        },
        defaults={},
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryIngestConfig,
        required={"source", "ipc_endpoint", "allowlist_events",
                  "queue_maxsize", "overflow_policy"},
        defaults={},
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryApiWriteConfig,
        required={
            "enabled",
            "intents_endpoint",
            "agent_intents_v2_endpoint",
            "rate_limit_per_min",
            "max_body_kb",
            "symbol_allowlist",
            "require_snapshot_ref",
            "idempotency_ttl_sec",
            "consequential",
            "legacy_execution_routes_enabled",
        },
        defaults={},
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryReadModelConfig,
        required={
            "enabled", "schema_version", "runtime_id", "environment",
            "context_stale_after_sec", "lifecycle_stale_after_sec", "max_items_per_section",
        },
        defaults={},
        class_factories={},
        dynamic_factories={},
    )
    assert ShadowTelemetryReadModelConfig is DomainShadowTelemetryReadModelConfig
    _assert_field_contract(
        ShadowTelemetryApiConfig,
        required={"enabled", "host", "port", "tls", "auth_mode", "read_model", "write"},
        defaults={},
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryEgressToMainConfig,
        required={"mode", "ipc_commands_endpoint",
                  "queue_maxsize", "overflow_policy"},
        defaults={},
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryTfPolicyConfig,
        required={"bar_snapshots_enabled", "tick_snapshots_mode",
                  "tick_sample_every_n", "min_tf_sec_for_full"},
        defaults={},
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryLedgerConfig,
        required={"queue_maxsize", "overflow_policy",
                  "enqueue_timeout_ms", "shutdown_timeout_ms"},
        defaults={},
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryLifecycleConfig,
        required={"stop_timeout_ms"},
        defaults={},
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetrySnapshotConfig,
        required={"trigger_event", "tf_policy", "output_dir"},
        defaults={},
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryDomainConfig,
        required={"enabled", "required_for_mode", "ingest", "api", "egress_to_main",
                  "ledger", "lifecycle", "agent_authority", "snapshot"},
        defaults={},
        class_factories={},
        dynamic_factories={},
    )


def test_shadow_telemetry_yaml_contract_fails_closed_on_invalid_tick_sampling(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["shadow_telemetry"]["snapshot"]["tf_policy"]["tick_sample_every_n"] = 0
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    loader = ConfigLoader(config_dir=cfg_dir)

    with pytest.raises(ValidationError) as exc_info:
        loader.load_config()

    message = str(exc_info.value)
    assert "tick_sample_every_n" in message
    assert "shadow_telemetry" in message


def test_shadow_telemetry_yaml_contract_fails_closed_on_invalid_ledger_queue_maxsize(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["shadow_telemetry"]["ledger"]["queue_maxsize"] = 0
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "queue_maxsize" in message
    assert "shadow_telemetry" in message


def test_shadow_telemetry_yaml_contract_fails_closed_on_invalid_ledger_overflow_policy(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["shadow_telemetry"]["ledger"]["overflow_policy"] = "drop_oldest"
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "overflow_policy" in message
    assert "shadow_telemetry" in message


def test_shadow_telemetry_yaml_contract_rejects_unknown_ledger_field(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["shadow_telemetry"]["ledger"]["unexpected"] = True
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected" in message
    assert "shadow_telemetry" in message


def test_shadow_telemetry_yaml_contract_fails_closed_on_invalid_lifecycle_stop_timeout(
    tmp_path: Path,
) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains["shadow_telemetry"]["lifecycle"]["stop_timeout_ms"] = 0
    domains_path.write_text(
        yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "stop_timeout_ms" in message
    assert "shadow_telemetry" in message
