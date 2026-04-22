import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config.domains.shadow_telemetry import (
    ShadowTelemetryApiConfig as DomainShadowTelemetryApiConfig,
    ShadowTelemetryApiWriteConfig as DomainShadowTelemetryApiWriteConfig,
    ShadowTelemetryDomainConfig as DomainShadowTelemetryDomainConfig,
    ShadowTelemetryEgressToMainConfig as DomainShadowTelemetryEgressToMainConfig,
    ShadowTelemetryIngestConfig as DomainShadowTelemetryIngestConfig,
    ShadowTelemetrySnapshotConfig as DomainShadowTelemetrySnapshotConfig,
    ShadowTelemetryTfPolicyConfig as DomainShadowTelemetryTfPolicyConfig,
)
from apps.reference.config_models import (
    ShadowTelemetryApiConfig,
    ShadowTelemetryApiWriteConfig,
    ShadowTelemetryDomainConfig,
    ShadowTelemetryEgressToMainConfig,
    ShadowTelemetryIngestConfig,
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
    assert st.api.auth_mode == "bearer"
    assert st.api.write.symbol_allowlist == ["1000PEPEUSDT"]
    assert st.api.write.require_snapshot_ref is True
    assert st.egress_to_main.mode == "ipc"
    assert st.egress_to_main.ipc_commands_endpoint == "tcp://127.0.0.1:7102"
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
    assert ShadowTelemetrySnapshotConfig is DomainShadowTelemetrySnapshotConfig
    assert ShadowTelemetryDomainConfig is DomainShadowTelemetryDomainConfig


def test_shadow_telemetry_extraction_preserves_field_contract() -> None:
    _assert_field_contract(
        ShadowTelemetryIngestConfig,
        required=set(),
        defaults={
            "source": "ipc_tap",
            "ipc_endpoint": "tcp://127.0.0.1:7101",
            "queue_maxsize": 50000,
            "overflow_policy": "fail_closed",
        },
        class_factories={},
        dynamic_factories={
            "allowlist_events": [
                "EVT:BAR_CLOSED",
                "EVT:FEATURES_CALCULATED",
                "EVT:TICK_FEATURES_CALCULATED",
                "EVT:RISK_ASSESSMENT_COMPLETED",
                "EVT:REGIME_DETECTED",
                "EVT:STRATEGY_SIGNAL_PRODUCED",
                "EVT:TRADE_INTENT_PROPOSED",
                "EVT:TRADE_INTENT_REJECTED",
                "EVT:INTENT_DEFERRED",
                "EVT:DECISION_BLOCKED",
                "EVT:STRATEGY_DECISION_BLOCKED",
                "EVT:ORDER_PLACED",
                "EVT:ORDER_REJECTED",
                "EVT:ORDER_STATE_CHANGED",
                "EVT:TRADE_EXECUTED",
                "EVT:POSITION_CLOSED",
            ],
        },
    )
    _assert_field_contract(
        ShadowTelemetryApiWriteConfig,
        required=set(),
        defaults={
            "enabled": True,
            "intents_endpoint": "/intents/llm/v1",
            "rate_limit_per_min": 30,
            "max_body_kb": 64,
            "require_snapshot_ref": True,
            "idempotency_ttl_sec": 300,
            "consequential": True,
        },
        class_factories={},
        dynamic_factories={
            "symbol_allowlist": ["BTCUSDT", "ETHUSDT"],
        },
    )
    _assert_field_contract(
        ShadowTelemetryApiConfig,
        required=set(),
        defaults={
            "enabled": True,
            "host": "0.0.0.0",
            "port": 8443,
            "tls": True,
            "auth_mode": "bearer",
        },
        class_factories={
            "write": ShadowTelemetryApiWriteConfig,
        },
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryEgressToMainConfig,
        required=set(),
        defaults={
            "mode": "ipc",
            "ipc_commands_endpoint": "tcp://127.0.0.1:7102",
            "queue_maxsize": 50000,
            "overflow_policy": "fail_closed",
        },
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryTfPolicyConfig,
        required=set(),
        defaults={
            "bar_snapshots_enabled": True,
            "tick_snapshots_mode": "sampled",
            "tick_sample_every_n": 20,
            "min_tf_sec_for_full": 60,
        },
        class_factories={},
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetrySnapshotConfig,
        required=set(),
        defaults={
            "trigger_event": "EVT:FEATURES_CALCULATED",
            "output_dir": "data/shadow_telemetry/snapshots",
        },
        class_factories={
            "tf_policy": ShadowTelemetryTfPolicyConfig,
        },
        dynamic_factories={},
    )
    _assert_field_contract(
        ShadowTelemetryDomainConfig,
        required=set(),
        defaults={
            "enabled": False,
            "required_for_mode": False,
        },
        class_factories={
            "ingest": ShadowTelemetryIngestConfig,
            "api": ShadowTelemetryApiConfig,
            "egress_to_main": ShadowTelemetryEgressToMainConfig,
            "snapshot": ShadowTelemetrySnapshotConfig,
        },
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
