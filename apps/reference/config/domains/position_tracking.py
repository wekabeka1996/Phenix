from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.config.shared.atoms import PrecisionConfig


class PositionTrackingDomainConfig(BaseModel):
    """Complete position tracking domain configuration.

    TASK-ZOMBIE-FIX: Removed thread_timeouts (dead, never read in runtime).
    """
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    precision: PrecisionConfig = Field(...)
    # TASK-ZOMBIE-FIX: Removed thread_timeouts (dead)
    positions_stale_ttl_sec: int = Field(
        ..., description='Portfolio freshness TTL for AuroraBridge gate')
    enable_market_tick_subscription: bool = Field(
        ..., description='Enable EVT:MARKET_TICK_RECEIVED subscription for mark-price PnL (optional)')
