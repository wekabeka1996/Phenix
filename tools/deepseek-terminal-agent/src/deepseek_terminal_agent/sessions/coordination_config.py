"""YAML/Pydantic source of truth for the P41X coordination kernel."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


REQUIRED_TOOL_NAMES = {
    "GET_MARKET_CONTEXT",
    "GET_FEATURES",
    "GET_PORTFOLIO_STATE",
    "GET_OWN_POSITIONS",
    "GET_PEER_PUBLICATIONS",
    "READ_COLLECTIVE_MEMORY",
    "PUBLISH_OBSERVATION",
    "PUBLISH_RISK_WARNING",
    "WRITE_PRIVATE_REFLECTION",
    "ASK_SUBAGENT",
    "REQUEST_ORDER",
    "REQUEST_CANCEL",
    "REQUEST_CLOSE",
    "EMIT_SOS",
    "ACK_INSTRUCTIONS",
}


class AgentIdentityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=1)
    interface: Literal["api", "cli"]
    symbols: list[str] = Field(..., min_length=1)

    @field_validator("symbols")
    @classmethod
    def normalized_symbols(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip().upper() for item in value]
        if any(not symbol for symbol in cleaned) or len(cleaned) != len(set(cleaned)):
            raise ValueError("symbols must be unique non-empty values")
        return cleaned


class SymbolLeaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ttl_seconds: int = Field(..., ge=1)
    heartbeat_expiry_seconds: int = Field(..., ge=1)


class TimerCadenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_refresh_seconds: int = Field(..., ge=1)
    agent_heartbeat_seconds: int = Field(..., ge=1)
    collective_sync_seconds: int = Field(..., ge=1)
    tactical_analysis_seconds: int = Field(..., ge=300)
    decision_review_seconds: int = Field(..., ge=900)
    portfolio_reconciliation_seconds: int = Field(..., ge=1)
    reflection_seconds: int = Field(..., ge=1)
    memory_checkpoint_seconds: int = Field(..., ge=1)
    instruction_manifest_refresh_seconds: int = Field(..., ge=1)
    event_wakeups: dict[str, list[str]]


class MemoryLimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_active_publications: int = Field(..., ge=1)
    active_context_token_limit: int = Field(..., ge=1)
    checkpoint_event_threshold: int = Field(..., ge=1)
    segment_size_events: int = Field(..., ge=1)
    max_summary_chars: int = Field(..., ge=64)
    token_estimate_chars_per_token: int = Field(..., ge=1)
    lock_timeout_seconds: float = Field(..., gt=0)
    lock_stale_seconds: float = Field(..., gt=0)
    max_private_reflections: int = Field(..., ge=1)
    critical_event_types: list[str] = Field(..., min_length=1)


class RetryPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(..., ge=1)
    backoff_ms: int = Field(..., ge=0)


class ToolPermissionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_agents: list[str] = Field(..., min_length=1)
    symbol_scope: Literal["owned", "all", "none"]
    timeout_seconds: int = Field(..., ge=1)
    retry: RetryPolicyConfig
    idempotency: Literal["required", "optional", "read_only"]
    permission: Literal["read", "publish", "private_write", "command", "ack"]


class PortfolioLimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_total_margin_usage: float = Field(..., gt=0)
    max_total_directional_exposure: float = Field(..., gt=0)
    max_correlated_exposure: float = Field(..., gt=0)
    max_global_drawdown_pct: float = Field(..., gt=0)
    emergency_stop_fails_closed: bool


class RecoveryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reacquire_expired_symbol_leases: bool
    require_exchange_reconciliation_for_dispatch_in_doubt: bool
    duplicate_submit_prevention_required: bool


class CoordinationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    environment: Literal["testnet"]
    agents: list[AgentIdentityConfig] = Field(..., min_length=2)
    symbol_leases: SymbolLeaseConfig
    timers: TimerCadenceConfig
    memory: MemoryLimitsConfig
    tool_permissions: dict[str, ToolPermissionConfig]
    portfolio_limits: PortfolioLimitsConfig
    recovery: RecoveryConfig

    @model_validator(mode="after")
    def validate_identity_and_tool_sets(self) -> "CoordinationConfig":
        agent_ids = [agent.agent_id for agent in self.agents]
        agent_numbers = [agent.agent_number for agent in self.agents]
        symbols = [symbol for agent in self.agents for symbol in agent.symbols]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("agent_id values must be unique")
        if len(agent_numbers) != len(set(agent_numbers)):
            raise ValueError("agent_number values must be unique")
        if len(symbols) != len(set(symbols)):
            raise ValueError("each symbol must have exactly one configured owner")
        if set(self.tool_permissions) != REQUIRED_TOOL_NAMES:
            missing = sorted(REQUIRED_TOOL_NAMES.difference(self.tool_permissions))
            extra = sorted(set(self.tool_permissions).difference(REQUIRED_TOOL_NAMES))
            raise ValueError(f"tool permission registry mismatch; missing={missing}, extra={extra}")
        known = set(agent_ids)
        for name, policy in self.tool_permissions.items():
            unknown = sorted(set(policy.allowed_agents).difference(known))
            if unknown:
                raise ValueError(f"tool {name} references unknown agents: {unknown}")
        return self

    def agent(self, agent_id: str) -> AgentIdentityConfig:
        for candidate in self.agents:
            if candidate.agent_id == agent_id:
                return candidate
        raise ValueError(f"unregistered agent_id: {agent_id}")

    def owner_for_symbol(self, symbol: str) -> AgentIdentityConfig:
        normalized = str(symbol or "").strip().upper()
        for candidate in self.agents:
            if normalized in candidate.symbols:
                return candidate
        raise ValueError(f"symbol has no configured owner: {normalized}")


DEFAULT_COORDINATION_CONFIG_PATH = Path(__file__).with_name("collective_memory_config.yaml")


def load_coordination_config(path: str | Path | None = None) -> CoordinationConfig:
    config_path = Path(path) if path is not None else DEFAULT_COORDINATION_CONFIG_PATH
    if not config_path.exists():
        raise RuntimeError(f"coordination config missing: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return CoordinationConfig.model_validate(raw)

