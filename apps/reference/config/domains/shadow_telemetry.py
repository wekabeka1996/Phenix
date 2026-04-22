from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class ShadowTelemetryIngestConfig(BaseModel):
    """Ingress settings for Shadow Telemetry event tap."""
    model_config = ConfigDict(extra='forbid')

    source: Literal["ipc_tap"] = Field(default="ipc_tap")
    ipc_endpoint: str = Field(default="tcp://127.0.0.1:7101")
    allowlist_events: List[str] = Field(
        default_factory=lambda: [
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
        ]
    )
    queue_maxsize: int = Field(default=50000, ge=1)
    overflow_policy: Literal["fail_closed",
                             "drop_oldest"] = Field(default="fail_closed")


class ShadowTelemetryApiWriteConfig(BaseModel):
    """Write-path HTTP controls for LLM intents."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(default=True)
    intents_endpoint: str = Field(default="/intents/llm/v1")
    rate_limit_per_min: int = Field(default=30, ge=1)
    max_body_kb: int = Field(default=64, ge=1)
    symbol_allowlist: List[str] = Field(
        default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    require_snapshot_ref: bool = Field(default=True)
    idempotency_ttl_sec: int = Field(default=300, ge=1)
    consequential: bool = Field(default=True)


class ShadowTelemetryApiConfig(BaseModel):
    """Shadow Telemetry API server settings."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(default=True)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8443, ge=1, le=65535)
    tls: bool = Field(default=True)
    auth_mode: Literal["bearer"] = Field(default="bearer")
    write: ShadowTelemetryApiWriteConfig = Field(
        default_factory=ShadowTelemetryApiWriteConfig)


class ShadowTelemetryEgressToMainConfig(BaseModel):
    """Egress command stream settings (Shadow -> Main)."""
    model_config = ConfigDict(extra='forbid')

    mode: Literal["ipc"] = Field(default="ipc")
    ipc_commands_endpoint: str = Field(default="tcp://127.0.0.1:7102")
    queue_maxsize: int = Field(default=50000, ge=1)
    overflow_policy: Literal["fail_closed",
                             "drop_oldest"] = Field(default="fail_closed")


class ShadowTelemetryTfPolicyConfig(BaseModel):
    """TF policy for snapshot generation."""
    model_config = ConfigDict(extra='forbid')

    bar_snapshots_enabled: bool = Field(default=True)
    tick_snapshots_mode: Literal["off", "sampled",
                                 "full"] = Field(default="sampled")
    tick_sample_every_n: int = Field(default=20, ge=1)
    min_tf_sec_for_full: int = Field(default=60, ge=0)


class ShadowTelemetrySnapshotConfig(BaseModel):
    """Snapshot capture controls."""
    model_config = ConfigDict(extra='forbid')

    trigger_event: str = Field(default="EVT:FEATURES_CALCULATED")
    tf_policy: ShadowTelemetryTfPolicyConfig = Field(
        default_factory=ShadowTelemetryTfPolicyConfig)
    output_dir: str = Field(default="data/shadow_telemetry/snapshots")


class ShadowTelemetryDomainConfig(BaseModel):
    """Top-level Shadow Telemetry domain config."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(default=False)
    required_for_mode: bool = Field(default=False)
    ingest: ShadowTelemetryIngestConfig = Field(
        default_factory=ShadowTelemetryIngestConfig)
    api: ShadowTelemetryApiConfig = Field(
        default_factory=ShadowTelemetryApiConfig)
    egress_to_main: ShadowTelemetryEgressToMainConfig = Field(
        default_factory=ShadowTelemetryEgressToMainConfig)
    snapshot: ShadowTelemetrySnapshotConfig = Field(
        default_factory=ShadowTelemetrySnapshotConfig)
