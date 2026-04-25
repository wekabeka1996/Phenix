from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class ShadowTelemetryIngestConfig(BaseModel):
    """Ingress settings for Shadow Telemetry event tap."""
    model_config = ConfigDict(extra='forbid')

    source: Literal["ipc_tap"] = Field(...)
    ipc_endpoint: str = Field(...)
    allowlist_events: List[str] = Field(
        ...)
    queue_maxsize: int = Field(..., ge=1)
    overflow_policy: Literal["fail_closed",
                             "drop_oldest"] = Field(...)


class ShadowTelemetryApiWriteConfig(BaseModel):
    """Write-path HTTP controls for LLM intents."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    intents_endpoint: str = Field(...)
    rate_limit_per_min: int = Field(..., ge=1)
    max_body_kb: int = Field(..., ge=1)
    symbol_allowlist: List[str] = Field(
        ...)
    require_snapshot_ref: bool = Field(...)
    idempotency_ttl_sec: int = Field(..., ge=1)
    consequential: bool = Field(...)


class ShadowTelemetryApiConfig(BaseModel):
    """Shadow Telemetry API server settings."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    host: str = Field(...)
    port: int = Field(..., ge=1, le=65535)
    tls: bool = Field(...)
    auth_mode: Literal["bearer"] = Field(...)
    write: ShadowTelemetryApiWriteConfig = Field(
        ...)


class ShadowTelemetryEgressToMainConfig(BaseModel):
    """Egress command stream settings (Shadow -> Main)."""
    model_config = ConfigDict(extra='forbid')

    mode: Literal["ipc"] = Field(...)
    ipc_commands_endpoint: str = Field(...)
    queue_maxsize: int = Field(..., ge=1)
    overflow_policy: Literal["fail_closed",
                             "drop_oldest"] = Field(...)


class ShadowTelemetryTfPolicyConfig(BaseModel):
    """TF policy for snapshot generation."""
    model_config = ConfigDict(extra='forbid')

    bar_snapshots_enabled: bool = Field(...)
    tick_snapshots_mode: Literal["off", "sampled",
                                 "full"] = Field(...)
    tick_sample_every_n: int = Field(..., ge=1)
    min_tf_sec_for_full: int = Field(..., ge=0)


class ShadowTelemetrySnapshotConfig(BaseModel):
    """Snapshot capture controls."""
    model_config = ConfigDict(extra='forbid')

    trigger_event: str = Field(...)
    tf_policy: ShadowTelemetryTfPolicyConfig = Field(
        ...)
    output_dir: str = Field(...)


class ShadowTelemetryDomainConfig(BaseModel):
    """Top-level Shadow Telemetry domain config."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    required_for_mode: bool = Field(...)
    ingest: ShadowTelemetryIngestConfig = Field(
        ...)
    api: ShadowTelemetryApiConfig = Field(
        ...)
    egress_to_main: ShadowTelemetryEgressToMainConfig = Field(
        ...)
    snapshot: ShadowTelemetrySnapshotConfig = Field(
        ...)
