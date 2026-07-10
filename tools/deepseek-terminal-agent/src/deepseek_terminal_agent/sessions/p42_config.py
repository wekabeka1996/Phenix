"""Pydantic config schemas for the P42 dual-agent trading arena."""
from __future__ import annotations

import pathlib
from typing import Dict, List, Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field

class TestnetOrderLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    max_orders: int = Field(..., ge=1)
    max_notional: float = Field(..., gt=0.0)

class AgentRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    runtime_kind: Literal["api", "cli"]
    symbols: List[str] = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    instruction_files: List[str] = Field(..., min_length=1)
    market_refresh_cadence_sec: int = Field(..., ge=1)
    analysis_cadence_sec: int = Field(..., ge=1)
    response_timeout_sec: int = Field(..., ge=1)
    retry_count: int = Field(..., ge=0)
    heartbeat_cadence_sec: int = Field(..., ge=1)
    collective_publication_cadence_sec: int = Field(..., ge=1)
    portfolio_sync_cadence_sec: int = Field(..., ge=1)
    reflection_cadence_sec: int = Field(..., ge=1)
    session_duration_sec: int = Field(..., ge=1)
    max_pending_commands: int = Field(..., ge=1)
    testnet_order_limits: TestnetOrderLimits
    startup_stagger_sec: int = Field(..., ge=0)
    shutdown_behavior: Literal["graceful", "immediate"]

class DualAgentMVPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    agents: Dict[str, AgentRuntimeConfig]


def load_dual_agent_config(path: str | pathlib.Path) -> DualAgentMVPConfig:
    """Loads and validates the DualAgentMVPConfig from a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return DualAgentMVPConfig(**data)
