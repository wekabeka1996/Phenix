from __future__ import annotations

from typing import List, Literal, Optional, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, model_validator


AllowedAction = Literal[
    "TESTNET_OPEN_LONG",
    "TESTNET_OPEN_SHORT",
    "TESTNET_CLOSE",
    "TESTNET_REDUCE",
    "WAIT",
    "OBSERVE",
    "NO_ACTION"
]

IntentSide = Literal["BUY", "SELL", "NONE"]


class AgentAuthorityDeepseekTestnetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    profile: Literal["deepseek_agent_only_testnet"]
    environment: Literal["testnet"]
    session_id: str
    agent_id: str
    provider: str
    model: str
    allowed_symbols: List[str]
    allowed_horizons: List[str]
    allowed_actions: List[AllowedAction]
    max_session_duration_sec: int = Field(..., ge=1)
    max_orders_per_session: int = Field(..., ge=1)
    max_orders_per_symbol: int = Field(..., ge=1)
    max_open_positions_total: int = Field(..., ge=1)
    max_open_positions_per_symbol: int = Field(..., ge=1)
    max_notional_per_order: float = Field(..., gt=0.0)
    max_total_notional: float = Field(..., gt=0.0)
    min_seconds_between_orders: int = Field(..., ge=0)
    duplicate_decision_window_sec: int = Field(..., ge=0)
    default_order_type: str = "LIMIT"
    default_time_in_force: str = "GTC"
    decision_timeout_sec: int = Field(..., ge=1)
    provider_timeout_sec: int = Field(..., ge=1)
    stop_on_first_execution_error: bool
    stop_on_unmatched_fill: bool
    stop_on_lifecycle_divergence: bool
    kill_switch_enabled: bool
    record_all_decisions: bool
    record_all_rejections: bool
    record_all_orders: bool


class AgentTradeDecisionV0(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent-trade-decision/v0"] = "agent-trade-decision/v0"
    agent_id: str = Field(..., min_length=3, max_length=120)
    provider: str
    model: str
    packet_ref: str = Field(..., pattern=r"^agent-feed://packet/afp_[a-f0-9]+$")
    symbol: str = Field(..., pattern=r"^[A-Z0-9_-]{2,32}$")
    horizon: str = Field(..., min_length=2, max_length=64)
    action: AllowedAction
    side: IntentSide
    confidence: float = Field(..., ge=0.0, le=1.0)
    thesis: str = Field(..., min_length=3, max_length=1000)
    invalidation: str = Field(..., min_length=3, max_length=1000)
    expected_scenarios: List[str] = Field(..., min_length=1, max_length=10)
    evidence_refs: List[str] = Field(..., min_length=1, max_length=20)
    acknowledged_warnings: List[str] = Field(default_factory=list, max_length=20)
    risk_note: str = Field(..., min_length=3, max_length=1000)
    testnet_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_action_side(self) -> AgentTradeDecisionV0:
        if self.action in {"WAIT", "OBSERVE", "NO_ACTION"} and self.side != "NONE":
            raise ValueError("Passive actions require side NONE")
        if self.action == "TESTNET_OPEN_LONG" and self.side != "BUY":
            raise ValueError("Open long requires side BUY")
        if self.action == "TESTNET_OPEN_SHORT" and self.side != "SELL":
            raise ValueError("Open short requires side SELL")
        if self.action in {"TESTNET_CLOSE", "TESTNET_REDUCE"} and self.side not in {"BUY", "SELL"}:
            raise ValueError("Close/Reduce actions require active side")
        return self


class AgentSessionStoppedV0(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(..., min_length=3, max_length=120)
