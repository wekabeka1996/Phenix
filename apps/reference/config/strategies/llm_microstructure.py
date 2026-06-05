from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.config.domains.decision_making import SafetyGatesConfig


class LLMMicrostructureStrategyConfig(BaseModel):
    """External-intent driven LLM strategy policy."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable llm_microstructure strategy')
    type: str = Field(..., description='Strategy type identifier')
    description: str = Field(
        ..., description='Human description of strategy profile')
    timeframe_sec: int = Field(..., ge=1, le=3600)
    pending_entry_ttl_ms: Optional[int] = Field(
        ..., ge=1000,
        description="Default valid_for_ms for external intents (ms). Fail-closed if absent and request omits it."
    )
    execution: "StrategyExecutionConfig" = Field(
        ..., description="Execution policy (SSOT)")
    safety_gates: SafetyGatesConfig = Field(..., description="Safety gates control")
