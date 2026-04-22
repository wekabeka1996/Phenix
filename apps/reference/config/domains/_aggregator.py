from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.config.domains.decision_making import DecisionMakingDomainConfig
from apps.reference.config.domains.execution_position import ExecutionPositionDomainConfig
from apps.reference.config.domains.feature_engineering import FeatureEngineeringDomainConfig
from apps.reference.config.domains.objective_engine import ObjectiveEngineDomainConfig
from apps.reference.config.domains.position_tracking import PositionTrackingDomainConfig
from apps.reference.config.domains.risk_management import RiskManagementDomainConfig
from apps.reference.config.domains.shadow_telemetry import ShadowTelemetryDomainConfig
from apps.reference.config.domains.ta_features import TAFeaturesDomainConfig


class DomainsDebugConfig(BaseModel):
    """Debug / shadow-only switches for domain gates (fail-closed in live/prod)."""

    model_config = ConfigDict(extra='forbid')

    disable_positions_stale_gate: bool = Field(
        description="DEV/SHADOW ONLY: disables position stale TTL gate (AuroraBridge portfolio freshness)."
    )
    disable_daily_loss_limit: bool = Field(
        description="DEV/SHADOW ONLY: disables daily loss/drawdown gate (RiskManagement DailyRiskState)."
    )


class DomainsConfig(BaseModel):
    """Top-level domains configuration container (CANONICAL)."""

    model_config = ConfigDict(
        extra='forbid'
    )  # CANONICAL: strict validation, fail-fast on unknown fields

    debug: DomainsDebugConfig = Field()
    decision_making: DecisionMakingDomainConfig = Field()
    feature_engineering: FeatureEngineeringDomainConfig = Field()
    ta_features: Optional[TAFeaturesDomainConfig] = Field(
        default=None,
        description="Separate TA feature core. Absent or enabled=false means no runtime wiring.",
    )
    risk_management: RiskManagementDomainConfig = Field()
    position_tracking: PositionTrackingDomainConfig = Field()
    execution_position: ExecutionPositionDomainConfig = Field()
    shadow_telemetry: ShadowTelemetryDomainConfig = Field(
        default_factory=ShadowTelemetryDomainConfig,
        description="Shadow telemetry domain (read/write LLM telemetry ingress)",
    )
    objective_engine: ObjectiveEngineDomainConfig = Field(
        default_factory=ObjectiveEngineDomainConfig,
        description="Objective Engine domain configuration",
    )
