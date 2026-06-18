from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.config.domains.decision_making import SafetyGatesConfig
from apps.reference.config.shared.atoms import StrategyIntentDecisionConfig


class LLMMicrostructureStrategyConfig(BaseModel):
    """External-intent driven LLM strategy policy."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable llm_microstructure strategy')
    mode: Literal['disabled', 'shadow', 'testnet_candidate', 'runtime'] = Field(
        ..., description='Financial authority mode for the strategy')
    type: str = Field(..., description='Strategy type identifier')
    description: str = Field(
        ..., description='Human description of strategy profile')
    timeframe_sec: int = Field(..., ge=1, le=3600)
    allowed_regimes: List[str] = Field(default_factory=list)
    allowed_sides: List[Literal['BUY', 'SELL']] = Field(
        default=['BUY', 'SELL'], min_length=1)
    pending_entry_ttl_ms: Optional[int] = Field(
        ..., ge=1000,
        description="Default valid_for_ms for external intents (ms). Fail-closed if absent and request omits it."
    )
    execution: "StrategyExecutionConfig" = Field(
        ..., description="Execution policy (SSOT)")
    decision: Optional[StrategyIntentDecisionConfig] = Field(default=None)
    objective: Optional["StrategyObjectiveConfig"] = Field(default=None)
    safety_gates: SafetyGatesConfig = Field(..., description="Safety gates control")
