"""Turn schemas for the P42 dual-agent trading arena."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

class AgentTurnContextEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    session_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_number: int = Field(..., ge=0)
    owned_symbols: List[str] = Field(..., min_length=1)
    current_market_context: Dict[str, Any] = Field(...)
    portfolio_state: Dict[str, Any] = Field(...)
    own_positions_orders: Dict[str, Any] = Field(...)
    peer_publications: List[Dict[str, Any]] = Field(...)
    instruction_versions: Dict[str, str] = Field(...)
    recent_decisions: List[Dict[str, Any]] = Field(...)
    allowed_tools: List[str] = Field(...)
    deadline: str = Field(..., min_length=1)
    current_collective_state_version: str = Field(..., min_length=1)

class AgentTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    action: Literal[
        "WAIT",
        "SKIP",
        "PUBLISH_OBSERVATION",
        "PUBLISH_RISK_WARNING",
        "REQUEST_ORDER",
        "REQUEST_CANCEL",
        "REQUEST_CLOSE",
        "REQUEST_REVIEW",
        "EMIT_SOS"
    ]
    payload: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(..., min_length=3)
    command_id: Optional[str] = None
    event_id: Optional[str] = None
