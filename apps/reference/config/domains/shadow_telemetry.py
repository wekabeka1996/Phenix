from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    agent_intents_v2_endpoint: str = Field(...)
    rate_limit_per_min: int = Field(..., ge=1)
    max_body_kb: int = Field(..., ge=1)
    symbol_allowlist: List[str] = Field(
        ...)
    require_snapshot_ref: bool = Field(...)
    idempotency_ttl_sec: int = Field(..., ge=1)
    consequential: bool = Field(...)
    legacy_execution_routes_enabled: bool = Field(...)


class ShadowTelemetryApiConfig(BaseModel):
    """Shadow Telemetry API server settings."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    host: str = Field(...)
    port: int = Field(..., ge=1, le=65535)
    tls: bool = Field(...)
    auth_mode: Literal["bearer", "loopback_optional_bearer"] = Field(...)
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


class ShadowTelemetryLedgerConfig(BaseModel):
    """Active decision outcome ledger queue controls."""

    model_config = ConfigDict(extra='forbid')

    queue_maxsize: int = Field(..., ge=1)
    overflow_policy: Literal["fail_closed"] = Field(...)
    enqueue_timeout_ms: int = Field(..., ge=0)
    shutdown_timeout_ms: int = Field(..., ge=1)


class ShadowTelemetryLifecycleConfig(BaseModel):
    """Shared bounded shutdown controls for active shadow telemetry surfaces."""

    model_config = ConfigDict(extra='forbid')

    stop_timeout_ms: int = Field(..., ge=1)


class AgentAuthorityPolicyConfig(BaseModel):
    """Static policy for the single-process V2 session authority."""

    model_config = ConfigDict(extra='forbid')

    config_version: str = Field(..., min_length=1)
    supported_session_statuses: List[Literal[
        "CREATED", "ACTIVE", "PAUSED", "CLOSED", "EXPIRED"
    ]] = Field(..., min_length=5, max_length=5)
    allowed_participant_types: List[Literal[
        "MAIN_AGENT", "SUBAGENT", "OPERATOR"
    ]] = Field(..., min_length=3, max_length=3)
    execution_capable_participant_types: List[Literal["MAIN_AGENT"]] = Field(
        ..., min_length=1, max_length=1
    )
    lease_ttl_sec: int = Field(..., ge=1)
    renewal_requires_owner: Literal[True] = Field(...)
    expiry_behavior: Literal["reject"] = Field(...)
    conflict_behavior: Literal["reject"] = Field(...)
    session_instrument_universe: List[str] = Field(..., min_length=1)
    max_position_horizon_sec: int = Field(..., ge=1)
    intent_ttl_sec: int = Field(..., ge=1)
    account_snapshot_max_age_sec: int = Field(..., ge=1)
    market_snapshot_max_age_sec: int = Field(..., ge=1)
    execution_order_type: Literal["LIMIT"] = Field(...)
    execution_time_in_force: Literal["GTC", "GTX", "IOC", "FOK"] = Field(...)
    execution_valid_for_ms: int = Field(..., ge=1000)
    context_ack_policy: Literal["defer_unavailable"] = Field(...)

    @field_validator("session_instrument_universe")
    @classmethod
    def normalize_universe(cls, value: List[str]) -> List[str]:
        normalized = [str(symbol).strip().upper() for symbol in value]
        if any(not symbol or not symbol.isalnum() for symbol in normalized):
            raise ValueError("session instrument symbols must be non-empty alphanumeric values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("session instrument symbols must be unique")
        return normalized

    @model_validator(mode="after")
    def exact_policy_sets(self) -> "AgentAuthorityPolicyConfig":
        if set(self.supported_session_statuses) != {
            "CREATED", "ACTIVE", "PAUSED", "CLOSED", "EXPIRED"
        }:
            raise ValueError("supported_session_statuses must declare the complete authority state set")
        if set(self.allowed_participant_types) != {"MAIN_AGENT", "SUBAGENT", "OPERATOR"}:
            raise ValueError("allowed_participant_types must declare the complete participant set")
        if self.execution_capable_participant_types != ["MAIN_AGENT"]:
            raise ValueError("only MAIN_AGENT may be execution-capable")
        return self


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
    ledger: ShadowTelemetryLedgerConfig = Field(
        ...)
    lifecycle: ShadowTelemetryLifecycleConfig = Field(
        ...)
    agent_authority: AgentAuthorityPolicyConfig = Field(...)
    snapshot: ShadowTelemetrySnapshotConfig = Field(
        ...)
