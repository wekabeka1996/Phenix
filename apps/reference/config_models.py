from __future__ import annotations

"""
Pydantic V2 configuration models for AuroraTrader.

This module defines the complete configuration schema with full type validation.
All models are designed to fail fast (startup validation) rather than silently accepting invalid configs.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Literal, Tuple
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from apps.reference.contracts.runtime_regime_layers import normalize_structural_regime_label
from apps.reference.config.shared.atoms import (
    BarGatingConfig,
    BehaviorFsmConfig,
    DirectionStrengthScoringConfig,
    KellyConfig,
    LiquidityGateConfig,
    PositionSizingConfig,
    PrecisionConfig,
    QosConfig,
    ROIExitConfig,
    SignalWeights,
    SignalsConfig,
)
from apps.reference.config.shared.decimal_utils import _coerce_positive_decimal
from apps.reference.config.shared.enums import (
    DangerZoneExitType,
    ExecutionGateName,
    OperationalMode,
)
from apps.reference.config.shared.instruments import (
    InstrumentExecutionConfig,
    InstrumentPrecisionSpec,
    InstrumentSizingConfig,
    InstrumentSpec,
    LeverageConfig,
)
from apps.reference.config.domains.objective_engine import (
    ObjectiveComponentConfig,
    ObjectiveDataRequirementsConfig,
    ObjectiveEngineDomainConfig,
    ObjectiveExplainabilityConfig,
    ObjectiveNormalizationConfig,
)
from apps.reference.config.domains.risk_management import (
    RiskManagementDomainConfig,
    RiskScoreWeightsConfig,
    RiskValidationConfig,
    TradingAllowedThresholdsConfig,
)
from apps.reference.config.domains.position_tracking import (
    PositionTrackingDomainConfig,
)
from apps.reference.config.domains.shadow_telemetry import (
    ShadowTelemetryApiConfig,
    ShadowTelemetryApiWriteConfig,
    ShadowTelemetryDomainConfig,
    ShadowTelemetryEgressToMainConfig,
    ShadowTelemetryIngestConfig,
    ShadowTelemetryLedgerConfig,
    ShadowTelemetryLifecycleConfig,
    ShadowTelemetrySnapshotConfig,
    ShadowTelemetryTfPolicyConfig,
)
from apps.reference.config.domains.ta_features import (
    TAFeaturesDomainConfig,
)
from apps.reference.config.domains.feature_engineering import (
    AbsorptionConfig,
    AbsorptionDedupConfig,
    AbsorptionProxyConfig,
    DeltaPriceConfig,
    DepthImbalanceConfig,
    EmaBiasConfig,
    EmaConfigDetailed,
    FeatureBoundsConfig,
    FeatureDefaultsConfig,
    FeatureEngineeringConfig,
    FeatureEngineeringDomainConfig,
    FeatureSanityConfig,
    LargeTradeImbalanceConfig,
    LegacyFeaturesLogConfig,
    LiquidityConfigDetailed,
    MacroResidConfig,
    MacroSyncMetricsConfig,
    OperatorConfig,
    PillarBackfillConfig,
    PillarWeightsConfig,
    PillarsConfig,
    SpreadBpsConfig,
    SpreadHealthGateConfig,
    StrategistConfig,
    TacticianConfig,
    VolatilityConfigDetailed,
    VolatilityStateConfig,
    VolumeConfigDetailed,
    VolumeSpikeConfig,
    VolumeZScoreConfig,
)
from apps.reference.config.domains.decision_making import (
    AnchorShockVetoConfig,
    ArmingConfig,
    ContextShieldConfig,
    DangerZoneShieldConfig,
    DashboardConfig,
    DecisionConfig,
    DecisionGeometryConfig,
    DecisionMakingDomainConfig,
    DecisionModeOverrideConfig,
    DegradedContextStrategyContractConfig,
    DirectionalSanityConfig,
    EntryPlanConfig,
    ExecutionGateConfig,
    ExitManagerConfig,
    FeaturesTtlConfig,
    FlipOrchestrationConfig,
    GlobalFlipKillswitchConfig,
    HoldingPeriodConfig,
    LowVolCostFloorFeeConfig,
    LowVolCostFloorGateConfig,
    LowVolCostFloorSlippageConfig,
    LowVolCostFloorThresholdsConfig,
    LowVolDirectionConfidenceConfig,
    LowVolGeometryConfig,
    MemoryShieldConfig,
    MoneyManagementConfig,
    PriceMotionSanityConfig,
    QuadraticRolloutConfig,
    ReadinessRegistryConfig,
    RegimeConfidenceGateConfig,
    RegimeLossEmbargoConfig,
    RegimeShiftInceptionConfig,
    RegimeSmoothingConfig,
    RiskGateConfig,
    RiskSkewConfig,
    SafetyGatesConfig,
    ScoringEngineConfig,
    StructuralGateConfig,
    VolAdjGatesConfig,
    WarmupEnforcementConfig,
)
from apps.reference.config.domains._aggregator import (
    DomainsConfig,
    DomainsDebugConfig,
)
from apps.reference.config.strategies.mean_reversion import (
    MRAssetConfig,
    MRDirectionalBiasConfig,
    MRMicrostructureVetoConfig,
    MRMomentumSeparationVetoConfig,
    MRRegimeSizingConfig,
    MRRegimeThresholdsConfig,
    MRSqueezeExpansionVetoConfig,
    MRStrategyOverrideConfig,
    MRStrategyParamsConfig,
    MeanReversion1mStrategyConfig,
)
from apps.reference.config.strategies.md_amr import (
    MDAMRAssetConfig,
    MDAMRConcentrationGuardConfig,
    MDAMRContextValidityConfig,
    MDAMREntryAnchorPersistenceConfig,
    MDAMRExitConfig,
    MDAMRHoldQualityConfig,
    MDAMRLLMGateConfig,
    MDAMROptunaConfig,
    MDAMRProgressTrackingConfig,
    MDAMRReconciliationConfig,
    MDAMRSetupQualityConfig,
    MDAMRStrategyConfig,
    MDAMRWeightsConfig,
    _MD_AMR_ALLOWED_REGIME_ALIASES,
    _MD_AMR_ALLOWED_REGIMES,
)
from apps.reference.config.strategies.llm_microstructure import (
    LLMMicrostructureStrategyConfig,
)
from apps.reference.config.strategies.aurora import (
    AuroraExecutionConfig,
    AuroraExitConfig,
    AuroraInstrumentConfig,
    AuroraSideBiasConfig,
    AuroraStrategyConfig,
    AuroraTakeProfitConfig,
    AuroraTrailingStopConfig,
    CANONICAL_WEIGHT_KEYS,
    EmaClampConfig,
    MaxRiskScoreConfig,
    RegimeTpSlConfig,
    SignalThresholdConfig,
    StrategyExecutionConfig,
    VolatilityEntryConfig,
)
from apps.reference.config.strategies.common import (
    StrategiesArbitrationConfig,
    StrategiesArbitrationLoggingConfig,
    StrategiesConfig,
    StrategiesRegistryConfig,
    StrategyObjectiveConfig,
    StrategyObjectiveGateConfig,
    StrategyObjectiveMultiplierConfig,
    StrategyObjectiveRegimeProfile,
)
from apps.reference.config.domains.execution_position import (
    AdvancedStaleCancelConfig,
    BracketHealthCheckConfig,
    BracketPlacementConfig,
    DriftAwayConfig,
    EventDedupConfig,
    EventDedupWarmStateConfig,
    ExecutionPositionDomainConfig,
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionRestoreArtifactMode,
    ExecutionPositionStartupTruthArtifactConfig,
    ExecutionPositionStartupTruthArtifactMode,
    ExecutionUtilsConfig,
    ExposureGuardConfig,
    FsmOpenConfig,
    GuardianConfig,
    IdempotentCancelConfig,
    InflightReconcileConfig,
    IntentBoundaryAuditConfig,
    MakerOnlyEntryConfig,
    MetricsCollectorConfig,
    OrderCapabilitiesConfig,
    OrderIndexConfig,
    OrderLifecycleConfig,
    PendingEntryTTLConfig,
    PositionPolicySidecarAllowedActionsConfig,
    PositionPolicySidecarConfig,
    PositionPolicySidecarFreshnessConfig,
    PositionPolicySidecarLoggingConfig,
    PositionPolicySidecarMode,
    PositionPolicySidecarPeakGivebackConfig,
    PositionPolicySidecarShadowPercentNotionalArmConfig,
    PositionPolicySidecarProfitabilityGuardConfig,
    PositionPolicySidecarScoringCapsConfig,
    PositionPolicySidecarScoringConfig,
    PositionPolicySidecarScoringWeightsConfig,
    PositionPolicySidecarStartupGraceConfig,
    PositionPolicySidecarThresholdsConfig,
    ShadowCheckConfig,
    SupersedeRepriceGuardConfig,
    _POSITION_POLICY_SIDECAR_CANONICAL_STRUCTURAL_REGIME_LABELS,
)
from apps.reference.config.system.observability import (
    AlertsConfig,
    ConsoleLogConfig,
    CoreLogSinkConfig,
    DomainLogConfig,
    EventChainLogConfig,
    LogRotationConfig,
    ObservabilityConfig,
    ObservabilityLoggingConfig,
    ShadowCriticalEventJournalConfig,
)
from apps.reference.config.system.market_data import (
    BarAggregatorConfig,
    MacroSyncConfig,
    MarketDataConfig,
    SystemMarketDataConfig,
)
from apps.reference.config.system.ops import OpsConfig
from apps.reference.telemetry.shadow_journal import DEFAULT_CRITICAL_EVENTS

# CONFIG_MODELS Phase 1 (2026-04-18): shared leaf atoms, enums, and helper
# utilities now live under apps.reference.config.shared and are re-exported
# here to preserve apps.reference.config_models as the public facade.


# TASK-ZOMBIE-FIX: Removed FailsafeConfig class (dead, max_hold_sec moved to AuroraExitConfig)


class MeanReversionConfig(BaseModel):
    """Configuration for Mean Reversion regime model (regime.yaml SSOT).

    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema, no runtime surprises).
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    bb_window: int = Field(...)
    bb_std_dev: float = Field(...)
    min_vol_atr: float = Field(...)
    allowed_regimes: List[str] = Field(...)


# Phase 2 / Pkg 7: resolve forward refs that still cross the frozen facade
# boundary after extracting the decision_making leaf module.
InstrumentPrecisionSpec.model_rebuild(
    _types_namespace={"FlipOrchestrationConfig": FlipOrchestrationConfig}
)
FeatureEngineeringDomainConfig.model_rebuild(
    _types_namespace={
        "ReadinessRegistryConfig": ReadinessRegistryConfig,
        "WarmupEnforcementConfig": WarmupEnforcementConfig,
    }
)
DecisionConfig.model_rebuild(
    _types_namespace={"MeanReversionConfig": MeanReversionConfig}
)


class SLConfig(BaseModel):
    """Stop-loss configuration."""
    model_config = ConfigDict(extra='forbid')
    fixed_bps: int = Field(..., description='Fixed basis points')


class TPConfig(BaseModel):
    """Take-profit configuration."""
    model_config = ConfigDict(extra='forbid')
    fixed_bps: int = Field(..., description='Fixed basis points')


class BracketsConfig(BaseModel):
    """Brackets (TP/SL) configuration."""
    model_config = ConfigDict(extra='forbid')

    sl: Optional[SLConfig] = Field(...)
    tp: Optional[TPConfig] = Field(...)
    oco_emulation: bool = Field(..., description='Emulate OCO orders')
    # TASK-ZOMBIE-FIX: Removed stop_loss_bps (dead duplicate, SSOT is sl.fixed_bps)
    offset_bps: int = Field(..., description='Safety offset in bps')


class TrailingDefaultsConfig(BaseModel):
    """Global trailing stop defaults (used when per-instrument not specified)."""
    model_config = ConfigDict(extra='forbid')

    activation_pct: float = Field(
        ..., description='0.3% profit to activate')
    trail_pct: float = Field(
        ..., description='0.6% trailing distance')
    min_update_interval_sec: int = Field(
        ..., description='Min seconds between updates')


class EmergencyConfig(BaseModel):
    """Emergency stop-loss configuration (margin-based).

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Added wait_mode_bars (fsm_manage.py:120).
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable emergency SL')
    wait_mode_bars: int = Field(
        ..., description='Wait mode bars before resuming')
    emergency_sl_bps: int = Field(
        ..., description='Emergency SL in basis points')


class OrphanMonitorConfig(BaseModel):
    """Orphan bracket monitor configuration.

    CFG-DICT-ANY-BURN-13: Typed config (consumption in fsm.py L166).
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable orphan monitoring')
    run_on_startup: bool = Field(
        ..., description='Run orphan check immediately on FSM startup')
    periodic_interval_sec: int = Field(
        ..., ge=5, description='Interval between orphan checks')
    min_order_age_sec: int = Field(
        ..., ge=0, description='Minimum age of order before considering it for orphan cleanup')
    batch_cancel_limit: int = Field(
        ..., ge=1, description='Max number of orders to cancel in one batch')
    rate_limit_per_min: int = Field(
        ..., ge=1, description='Rate limit for cancel requests per minute')


class ManageConfig(BaseModel):
    """Order management configuration.

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields typed).
    """
    model_config = ConfigDict(extra='forbid')

    brackets: Optional[BracketsConfig] = Field(...)
    emergency: Optional[EmergencyConfig] = Field(...)
    auto: bool = Field(...)
    orphan_monitor: Optional[OrphanMonitorConfig] = Field(...)
    # TASK-ZOMBIE-FIX: Removed failsafe field (dead, max_hold_sec moved to instruments.<SYM>.exit)


class ExposureConfig(BaseModel):
    """Exposure guard configuration.

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields known).
    """
    model_config = ConfigDict(extra='forbid')

    max_equity_utilization_pct: float = Field(...)
    max_portfolio_fraction: float = Field(...)
    # TASK-ZOMBIE-FIX: Removed max_side_utilization_pct (dead, never read in exposure_guard)
    max_directional_ratio: float = Field(...)
    # TASK-ZOMBIE-FIX: Removed per_symbol_cap_pct (dead, never read in exposure_guard)
    pending_ttl_sec: int = Field(...)
    # TASK-ZOMBIE-FIX: Removed pending_reservation_ttl_sec (dead, never read in exposure_guard)
    post_fill_hold_ttl_sec: int = Field(...)
    # TASK-ZOMBIE-FIX: Removed positions_stale_ttl_sec (duplicate, SSOT is domains.execution_position.exposure_guard.stale_ttl_sec)
    leverage_defaults: Dict[str, int] = Field(...)
    count_pending_orders: bool = Field(
        ..., description='Count pending orders in exposure')
    exclude_reduce_only: bool = Field(
        ..., description='Exclude reduce-only from exposure')


class WatchdogConfig(BaseModel):
    """Watchdog configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    ack_ttl_ms: int = Field(...)
    fill_ttl_ms: int = Field(...)
    check_interval_ms: int = Field(...)
    rps_limit: int = Field(...)


class SMARegimeModelConfig(BaseModel):
    """Configuration for SMA-based trend regime detection.

    Detects TREND_UP, TREND_DOWN, MEAN_REVERSION based on SMA crossover.
    """
    model_config = ConfigDict(extra='forbid')

    sma_short_period: int = Field(
        ..., ge=2, description='Short SMA period for trend detection')
    sma_long_period: int = Field(
        ..., ge=5, description='Long SMA period for trend detection')
    confidence_multiplier: float = Field(
        ..., ge=1.0, description='Confidence scaling factor')
    confidence_min: float = Field(
        ..., ge=0.0, le=1.0, description='Minimum confidence value')
    confidence_max: float = Field(
        ..., ge=0.0, le=1.0, description='Maximum confidence value')


class VolatilityRegimeModelConfig(BaseModel):
    """Configuration for ATR-based volatility regime detection.

    Detects HIGH_VOLATILITY, LOW_VOLATILITY based on ATR vs historical average.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...,
                          description='Enable volatility regime detection')
    atr_period: int = Field(..., ge=1, description='ATR calculation period')
    atr_sma_length: int = Field(
        ..., ge=10, description='ATR SMA length for baseline')
    allow_close_to_close_atr: bool = Field(
        ..., description='Allow close-to-close TR/ATR when OHLC is unavailable (explicit opt-in)')
    threshold_multiplier: float = Field(
        ..., ge=1.0, description='High vol threshold (ATR > threshold_mult * avg)')
    low_vol_multiplier: float = Field(
        ..., ge=0.0, le=1.0, description='Low vol threshold (ATR < low_vol_mult * avg)')
    high_vol_confidence_multiplier: float = Field(
        ..., ge=1.0, description='Confidence scaling for high vol')
    low_vol_confidence_multiplier: float = Field(
        ..., ge=1.0, description='Confidence scaling for low vol')


class MeanReversionRegimeModelConfig(BaseModel):
    """Configuration for mean reversion regime detection.

    Detects MEAN_REVERSION when price is close to both SMAs.
    """
    model_config = ConfigDict(extra='forbid')

    threshold: float = Field(
        ..., ge=0.0, description='Max price deviation from SMAs for MR regime')
    confidence_multiplier: float = Field(
        ..., ge=1.0, description='Confidence scaling factor')


class RegimeModelsConfig(BaseModel):
    """Container for all regime detection model configurations.

    Loaded from regime.yaml 'models' section.

    CFG-FEATURES-REGIME-SSOT-04: extra='forbid' for strict validation
    """
    model_config = ConfigDict(extra='forbid')

    sma_trend: SMARegimeModelConfig = Field(..., description='SMA trend model')
    volatility: VolatilityRegimeModelConfig = Field(
        ..., description='Volatility model')
    mean_reversion: MeanReversionRegimeModelConfig = Field(
        ..., description='Mean reversion model')


class RegimeModelConfig(BaseModel):
    """Base configuration for regime detection models.

    CONFIG_MODELS Phase 0 (2026-04-18): no runtime parent attaches this
    class as a Pydantic field. Sole consumer is the docs path-mapping
    tool ``tools/docs_gen/generate_config_default_path_map.py`` which
    introspects it for documentation generation. Retained verbatim for
    that consumer; do not extend or attach to a runtime config tree.
    The active runtime container is :class:`RegimeModelsConfig` (plural).
    """
    model_config = ConfigDict(extra='forbid')

    confidence_multiplier: float = Field(...)
    confidence_min: float = Field(...)
    confidence_max: float = Field(...)


class RegimeDetectorConfig(BaseModel):
    """Regime detector configuration."""
    model_config = ConfigDict(extra='forbid')

    models: RegimeModelsConfig = Field(
        ..., description='Regime detection models config')


# ═══════════════ SYSTEM STRESS GUARD (Phase 0.0) ═══════════════
# Independent circuit-breaker overlay: NORMAL → STRESS → EXTREME.
# Not a replacement for TREND/MR regimes — a separate guard layer.

# Canonical trigger keys for weight validation
STRESS_TRIGGER_KEYS = frozenset(
    {"atr", "vol", "gap", "range", "volume", "spread", "depth"})
# Price-only triggers (no orderbook required)
STRESS_PRICE_TRIGGERS = frozenset({"atr", "vol", "gap", "range", "volume"})
# Orderbook-only triggers
STRESS_ORDERBOOK_TRIGGERS = frozenset({"spread", "depth"})


class SystemStressThresholdsConfig(BaseModel):
    """Sigma thresholds for individual stress indicators.

    0.0 = disabled for that trigger (explicitly opt-out).
    """
    model_config = ConfigDict(extra='forbid')

    atr_sigma: float = Field(
        ..., ge=0.0, le=10.0, description='ATR z-score threshold')
    vol_sigma: float = Field(
        ..., ge=0.0, le=10.0, description='Realized vol z-score threshold')
    gap_sigma: float = Field(
        ..., ge=0.0, le=10.0, description='Bar gap z-score threshold')
    range_sigma: float = Field(
        ..., ge=0.0, le=10.0, description='Bar range z-score threshold')
    volume_sigma: float = Field(
        ..., ge=0.0, le=10.0, description='Volume z-score (0.0=disabled)')
    spread_sigma: float = Field(
        ..., ge=0.0, le=10.0, description='Spread z-score (orderbook only)')
    depth_drop_pct: float = Field(
        ..., ge=0.0, le=100.0, description='Depth drop % (orderbook only, 0.0=disabled)')


class SystemStressAggregationConfig(BaseModel):
    """How to combine individual stress trigger signals into a composite score."""
    model_config = ConfigDict(extra='forbid')

    method: Literal["weighted_vote", "k_of_n", "max"] = Field(
        ..., description='Aggregation method for stress triggers'
    )
    weights: Optional[Dict[str, float]] = Field(
        ..., description='Trigger weights (required if method=weighted_vote). Keys must be from STRESS_TRIGGER_KEYS.'
    )
    k: Optional[int] = Field(
        ..., ge=1,
        description='Minimum triggers required (required if method=k_of_n)'
    )

    @model_validator(mode='after')
    def _validate_method_deps(self) -> 'SystemStressAggregationConfig':
        if self.method == "weighted_vote":
            if not self.weights:
                raise ValueError(
                    "aggregation.weights required when method=weighted_vote")
            # Validate keys are from canonical set
            invalid = set(self.weights.keys()) - STRESS_TRIGGER_KEYS
            if invalid:
                raise ValueError(
                    f"aggregation.weights invalid keys: {sorted(invalid)}. "
                    f"Allowed: {sorted(STRESS_TRIGGER_KEYS)}"
                )
            total = sum(self.weights.values())
            if abs(total - 1.0) > 0.01:
                raise ValueError(
                    f"aggregation.weights must sum to ~1.0, got {total:.4f}")
        if self.method == "k_of_n" and self.k is None:
            raise ValueError("aggregation.k required when method=k_of_n")
        return self


class SystemStressStateMappingConfig(BaseModel):
    """Hysteresis state transitions NORMAL → STRESS → EXTREME.

    Ordering invariants enforced:
    - exit_stress < enter_stress < enter_extreme
    - exit_extreme < enter_extreme
    """
    model_config = ConfigDict(extra='forbid')

    enter_stress: float = Field(
        ..., ge=0.0, le=1.0, description='Composite score to enter STRESS')
    exit_stress: float = Field(
        ..., ge=0.0, le=1.0, description='Composite score to exit STRESS → NORMAL')
    enter_extreme: float = Field(
        ..., ge=0.0, le=1.0, description='Composite score to enter EXTREME')
    exit_extreme: float = Field(
        ..., ge=0.0, le=1.0, description='Composite score to exit EXTREME → STRESS')
    consecutive_bars_enter: int = Field(
        ..., ge=1, le=20, description='Consecutive bars above threshold to confirm entry')
    consecutive_bars_exit: int = Field(
        ..., ge=1, le=20, description='Consecutive bars below threshold to confirm exit')
    min_duration_bars: int = Field(
        ..., ge=0, le=100, description='Minimum bars to stay in a state before allowing exit')
    switch_window_bars: int = Field(
        ..., ge=1, description='Rolling window (bars) for switch counting')
    max_switches_per_window: int = Field(
        ..., ge=1, le=50, description='Max state switches in window before circuit breaker')
    circuit_breaker_mode: Literal["halt"] = Field(
        ..., description='Action on max_switches breach. halt = fail-closed (block all entries).'
    )

    @model_validator(mode='after')
    def _validate_ordering(self) -> 'SystemStressStateMappingConfig':
        if self.exit_stress >= self.enter_stress:
            raise ValueError(
                f"exit_stress ({self.exit_stress}) must be < enter_stress ({self.enter_stress}) (hysteresis)"
            )
        if self.exit_extreme >= self.enter_extreme:
            raise ValueError(
                f"exit_extreme ({self.exit_extreme}) must be < enter_extreme ({self.enter_extreme}) (hysteresis)"
            )
        if self.enter_stress >= self.enter_extreme:
            raise ValueError(
                f"enter_stress ({self.enter_stress}) must be < enter_extreme ({self.enter_extreme})"
            )
        return self


class SystemStressConfig(BaseModel):
    """System-wide stress overlay (independent of TREND/MR regimes).

    When enabled, monitors market microstructure for abnormal conditions
    and emits NORMAL/STRESS/EXTREME state for DM gating.
    Disabled by default (None at AuroraConfig root = off).
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...,
                          description='Master enable (off by default in YAML)')
    sources_enabled: List[Literal["price", "orderbook"]] = Field(
        ..., min_length=1,
        description='Data sources required. "price" = OHLCV only. "orderbook" = L2 required.'
    )
    require_l2_if_enabled: bool = Field(
        ..., description='Fail-fast if "orderbook" in sources_enabled but L2 data is unavailable'
    )
    baseline_method: Literal["rolling", "expanding"] = Field(
        ..., description='Baseline method for z-score calculation'
    )
    baseline_window: Optional[int] = Field(
        ..., ge=10,
        description='Rolling window size (bars). REQUIRED if baseline_method=rolling.'
    )
    burn_in_bars: int = Field(
        ..., ge=1,
        description='Minimum bars before stress signal is emitted (warmup period)'
    )
    robust_method: Literal["none", "mad"] = Field(
        ..., description='Robust statistics method (none=std, mad=median absolute deviation)'
    )
    thresholds: SystemStressThresholdsConfig = Field(
        ..., description='Per-trigger sigma thresholds (0.0 = disabled for that trigger)'
    )
    aggregation: SystemStressAggregationConfig = Field(
        ..., description='How to combine trigger signals'
    )
    state_mapping: SystemStressStateMappingConfig = Field(
        ..., description='Hysteresis rules for NORMAL/STRESS/EXTREME transitions'
    )

    @model_validator(mode='after')
    def _validate_rolling_window(self) -> 'SystemStressConfig':
        if self.baseline_method == "rolling" and self.baseline_window is None:
            raise ValueError(
                "baseline_window required when baseline_method=rolling")
        return self

    @model_validator(mode='after')
    def _validate_orderbook_triggers(self) -> 'SystemStressConfig':
        """If orderbook not in sources_enabled, orderbook-only thresholds must be 0."""
        has_orderbook = "orderbook" in self.sources_enabled
        if not has_orderbook:
            if self.thresholds.spread_sigma > 0:
                raise ValueError(
                    "spread_sigma > 0 requires 'orderbook' in sources_enabled"
                )
            if self.thresholds.depth_drop_pct > 0:
                raise ValueError(
                    "depth_drop_pct > 0 requires 'orderbook' in sources_enabled"
                )
        return self

    @model_validator(mode='after')
    def _validate_weight_keys_match_active_triggers(self) -> 'SystemStressConfig':
        """Weight keys must correspond to triggers that are actually enabled (>0)."""
        if self.aggregation.method != "weighted_vote" or not self.aggregation.weights:
            return self

        # Build set of active trigger keys from thresholds
        threshold_map = {
            "atr": self.thresholds.atr_sigma,
            "vol": self.thresholds.vol_sigma,
            "gap": self.thresholds.gap_sigma,
            "range": self.thresholds.range_sigma,
            "volume": self.thresholds.volume_sigma,
            "spread": self.thresholds.spread_sigma,
            "depth": self.thresholds.depth_drop_pct,
        }
        active_triggers = {k for k, v in threshold_map.items() if v > 0}
        weight_keys = set(self.aggregation.weights.keys())

        # Weights for disabled triggers (waste, likely a typo)
        wasted = weight_keys - active_triggers
        if wasted:
            raise ValueError(
                f"aggregation.weights has keys for disabled triggers (sigma=0): {sorted(wasted)}. "
                "Remove them or enable the trigger."
            )
        return self


class FallbackConfig(BaseModel):
    """Explicit fail-closed execution safety policy."""
    model_config = ConfigDict(extra='forbid')

    policy: Literal["fail_closed"] = Field(
        ..., description="Only supported safety policy: block new orders when execution truth is unavailable."
    )


# Phase 2 / Pkg 8: resolve the single frozen-facade cross-boundary ref
# after extracting the execution_position leaf module.
ExecutionPositionDomainConfig.model_rebuild(
    _types_namespace={"FallbackConfig": FallbackConfig}
)


class LimitOrdersConfig(BaseModel):
    """Limit orders configuration.

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: legacy typed placeholder for the null
    compatibility surface under trading.execution.limit_orders.

    J3/J4 audit (2026-04-30): Reserved null compatibility surface only.
    Zero runtime consumers — no EP/watchdog/FSM code reads this config.
    Active timeout SSOT: OrderTimeoutWatchdog + domains.execution_position.pending_entry_ttl.
    Staged retirement pending external compatibility audit (J5).
    """
    model_config = ConfigDict(extra='forbid')

    # Add fields when consumption patterns documented


class OrdersConfig(BaseModel):
    """Orders configuration (TTL, retries, etc.).

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Typed (fsm.py:282 default_ttl_seconds).
    """
    model_config = ConfigDict(
        extra='forbid')  # Temporary: market/cancel sub-configs unknown

    default_ttl_seconds: int = Field(..., description='Default order TTL')


class ExecutionConfig(BaseModel):
    """Execution configuration.

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields explicit).
    """
    model_config = ConfigDict(extra='forbid')

    manage: Optional[ManageConfig] = Field(...)
    exposure: Optional[ExposureConfig] = Field(...)
    # Typed (ack_ttl_ms, fill_ttl_ms, rps_limit)
    watchdog: Optional[WatchdogConfig] = Field(...)

    # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Newly typed configs
    fallback: Optional[FallbackConfig] = Field(...)
    limit_orders: Optional[LimitOrdersConfig] = Field(...)
    orders: Optional[OrdersConfig] = Field(...)

    # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Explicit runtime fields (consumption proven)
    fsm_periodic_cleanup_enabled: bool = Field(
        ..., description='FSM periodic cleanup')
    cooldown_after_close_ms: int = Field(
        ...,
        description="Global cooldown after any position closes (ms). Blocks new CMD:OPEN during this window.",
    )
    anti_race_close_ms: int = Field(..., description='Anti-race window (ms)')

    # PURGE-DIRTY-DOZEN: Removed dead fields (open_order_type, min_post_interval_per_symbol_ms) - 2026-01-25
    # Remaining DEPRECATED fields kept for backward compat parsing only:
    order_params: Optional[Dict[str, Any]] = Field(
        ..., description='DEPRECATED: No consumption found')
    preflight_backoff_ms: Optional[List[int]] = Field(
        ..., description='DEPRECATED: No consumption found')
    allow_trade_with_guardian_tidy_only: Optional[bool] = Field(
        ..., description='DEPRECATED')
    order_guardian: Optional[Dict[str, Any]] = Field(
        ..., description='DEPRECATED: Guardian not config')


# Position Tracking Domain


# TASK-ZOMBIE-FIX: Removed ThreadTimeoutsConfig class (dead, join_timeout_sec never read in runtime)
AuroraStrategyConfig.model_rebuild(
    _types_namespace={"StrategyObjectiveConfig": StrategyObjectiveConfig}
)


MeanReversion1mStrategyConfig.model_rebuild(
    _types_namespace={
        "StrategyExecutionConfig": StrategyExecutionConfig,
        "StrategyObjectiveConfig": StrategyObjectiveConfig,
    }
)

LLMMicrostructureStrategyConfig.model_rebuild(
    _types_namespace={"StrategyExecutionConfig": StrategyExecutionConfig}
)

MDAMRExitConfig.model_rebuild(
    _types_namespace={"RegimeTpSlConfig": RegimeTpSlConfig}
)

MDAMRAssetConfig.model_rebuild(
    _types_namespace={
        "MDAMRExitConfig": MDAMRExitConfig,
        "RegimeTpSlConfig": RegimeTpSlConfig,
    }
)

MDAMRStrategyConfig.model_rebuild(
    _types_namespace={
        "StrategyExecutionConfig": StrategyExecutionConfig,
        "StrategyObjectiveConfig": StrategyObjectiveConfig,
    }
)

StrategiesConfig.model_rebuild(
    _types_namespace={
        "AuroraStrategyConfig": AuroraStrategyConfig,
        "MeanReversion1mStrategyConfig": MeanReversion1mStrategyConfig,
        "MDAMRStrategyConfig": MDAMRStrategyConfig,
        "LLMMicrostructureStrategyConfig": LLMMicrostructureStrategyConfig,
        "StrategyObjectiveConfig": StrategyObjectiveConfig,
    }
)


# ==============================================================================
# DOMAIN CONFIGURATION (Hybrid Mode: live data → testnet execution)
# ==============================================================================
class DomainModeConfig(BaseModel):
    """Configuration for a single domain's trading mode."""
    model_config = ConfigDict(extra='forbid')

    trading_mode: Literal["live", "testnet"] = Field(
        ...,  # REQUIRED - no default!
        description="Trading mode for this domain: 'live' or 'testnet'"
    )


class DomainConfigurationConfig(BaseModel):
    """
    Domain-level mode configuration for hybrid trading.

    Hybrid mode allows:
    - Data domains (market_data, feature_engineering, decision_making) → LIVE
    - Execution domains (execution_position, risk_management) → TESTNET

    CRITICAL: For production, explicitly set each domain's mode!
    Default is all-testnet for safety in tests.
    """
    model_config = ConfigDict(extra='forbid')

    # ALIVE: Used by preflight.py for hybrid mode coherence check
    market_data: DomainModeConfig = Field(
        ..., description="Market data source mode (should be 'live' for real prices)")
    feature_engineering: DomainModeConfig = Field(
        ..., description='Feature engineering mode (should match market_data)')
    decision_making: DomainModeConfig = Field(
        ..., description='Decision making mode (should match market_data)')
    # PURGE-DIRTY-DOZEN: Made optional (dead, global trading_mode is SSOT) - 2026-01-25
    risk_management: Optional[DomainModeConfig] = Field(
        ..., description='DEPRECATED: Use global trading_mode')
    execution_position: Optional[DomainModeConfig] = Field(
        ..., description='DEPRECATED: Use global trading_mode')
    audit_trail: Optional[DomainModeConfig] = Field(
        ..., description='DEPRECATED: Use global trading_mode')


# SCORCHED-EARTH-2026-01-27: Typed TCAPrefsConfig (was Dict[str, Any])
class TCAPrefsConfig(BaseModel):
    """Transaction Cost Analysis (TCA) preferences."""
    model_config = ConfigDict(extra='forbid')

    max_slippage_pct: float = Field(
        ..., description="Max allowed slippage %")
    max_slippage_bps: int = Field(
        ..., description="Max allowed slippage in basis points")
    max_latency_ms: int = Field(
        ..., description="Max allowed latency (intent to filled) in ms")
    maker_preference: Literal["maker", "taker", "neutral", "any"] = Field(
        ..., description="Execution preference (maker/taker/neutral)"
    )
    preferred_venue: str = Field(
        ..., description="Preferred execution venue")
    execution_priority: Literal["speed", "price", "balanced"] = Field(
        ..., description="Execution priority: speed (market) vs price (limit)"
    )


# SCORCHED-EARTH-2026-01-27: Typed RiskBudgetsConfig (was Dict[str, Any])
class RiskBudgetsConfig(BaseModel):
    """Risk budgeting configuration."""
    model_config = ConfigDict(extra='forbid')

    trade_cvar95_max_bps: int = Field(...,
                                      description="Max CVaR-95 per trade (bps)")
    session_cvar95_max_bps: int = Field(...,
                                        description="Max CVaR-95 per session (bps)")
    max_portfolio_risk_pct: float = Field(...,
                                          description="Max total portfolio risk %")
    max_single_position_risk_pct: float = Field(
        ..., description="Max single position risk %")
    max_daily_loss_pct: float = Field(..., description="Max daily loss %")


class LLMIntentPolicyConfig(BaseModel):
    """Policy limits for external LLM intents."""
    model_config = ConfigDict(extra='forbid')

    max_open_intents: int = Field(..., ge=1)
    cooldown_sec: int = Field(..., ge=0)
    allow_limit_only: bool = Field(...)
    require_tp_sl: bool = Field(...)
    max_notional_usd: Optional[float] = Field(..., gt=0.0)
    max_qty: Optional[float] = Field(..., gt=0.0)
    max_price_deviation_bps: Optional[float] = Field(..., gt=0.0)
    allowed_tif: List[Literal["GTC"]] = Field(...)


class LLMOrchestrationConfig(BaseModel):
    """Global LLM orchestration mode and policy."""
    model_config = ConfigDict(extra='forbid')

    mode: Literal["baseline", "hybrid_advisory",
                  "llm_primary"] = Field(...)
    llm_role: Literal["advisory", "filter",
                      "primary"] = Field(...)
    require_telemetry: bool = Field(...)
    symbols_llm: List[str] = Field(...)
    allowlist_symbols: List[str] = Field(
        ...)
    intent_policy: LLMIntentPolicyConfig = Field(
        ...)


class TradingConfig(BaseModel):
    """Main trading configuration (with mode overrides)."""
    model_config = ConfigDict(extra='forbid')

    mode: str = Field(..., description='testnet | production | live')
    execution: Optional[ExecutionConfig] = Field(...)
    symbols_to_track: List[str] = Field(
        ...,
        description=(
            "List of symbols to track for multi-TF aggregation. "
            "Derived deterministically from strategies.yaml assignments by ConfigLoader unless explicitly set."
        ),
    )
    market_data: Optional[MarketDataConfig] = Field(...)

    # NOTE (TASK23.FIX.B): Forbidden SSOT mirrors are intentionally NOT part of TradingConfig.
    # - instruments SSOT: root.instruments (config/aurora/instruments.yaml)
    # - aurora per-symbol SSOT: strategies/aurora.yaml::aurora.assets (canonical: config.strategies.aurora.assets)
    # - domains SSOT: root.domains (config/aurora/domains.yaml)
    # - feature_engineering SSOT: domains.yaml (domain config), not trading.yaml

    # Legacy risk config (still used by DailyRiskState etc)
    risk: Dict[str, Any] = Field(
        ..., description='Legacy risk configuration (daily gate, etc)')

    # TCA and Risk Budgets (Strictly Typed)
    tca_prefs: TCAPrefsConfig = Field(..., description='TCA Preferences')
    risk_budgets: RiskBudgetsConfig = Field(
        ..., description='Risk Budgeting Configuration')

    # Risk management data sources (used for hybrid/live/testnet wiring)
    risk_management: "TradingRiskManagementConfig" = Field(...)

    # Ops configuration (killswitch, quiet hours)
    ops: Optional[OpsConfig] = Field(
        ..., description='Operations config (panic killswitch, quiet hours, allowlist)')
    llm_orchestration: LLMOrchestrationConfig = Field(
        ..., description="Global orchestration policy for shadow-LLM strategies",
    )

    # CRITICAL: Domain-level mode configuration (Hybrid Mode)
    # Default is all-testnet for safety. Production MUST explicitly set live modes!
    domain_configuration: DomainConfigurationConfig = Field(
        ..., description='Domain-level trading mode configuration for hybrid mode (live data + testnet execution)')

    # Regime-specific TP/SL multipliers (for backtest overrides)
    regime_tpsl: Optional[Dict[str, Any]] = Field(
        ..., description="Regime-specific TP/SL multipliers")

    @field_validator("symbols_to_track")
    @classmethod
    def _validate_symbols_to_track(cls, v: Any) -> List[str]:
        if not isinstance(v, list) or not v:
            raise ValueError(
                "trading.symbols_to_track must be a non-empty list")
        return [str(s) for s in v]


class BinanceApiEnv(BaseModel):
    """Binance API configuration for a single environment."""
    model_config = ConfigDict(extra='forbid')

    api_key: Optional[str] = Field(...)
    api_secret: Optional[str] = Field(...)
    rest_url: Optional[str] = Field(...)
    # PURGE-DEAD-CONFIG-03: ws_url removed (hardcoded in market_data_connector.py, worker.py)


class BinanceApiConfig(BaseModel):
    """Binance API configuration (live + testnet)."""
    model_config = ConfigDict(extra='forbid')
    live: BinanceApiEnv = Field(...)
    testnet: BinanceApiEnv = Field(...)


# NOTE: RetrySchedulerConfig and BridgeConfig removed (BRIDGE-SUNSET-01)
# AuroraBridge was removed; ExecPosFSM now handles TRADE_INTENT_PROPOSED directly.


class RiskManagementDataSourcesConfig(BaseModel):
    """Runtime data source selection for risk management."""
    model_config = ConfigDict(extra='forbid')

    market_data: Literal["live", "testnet"] = Field(...)
    portfolio_state: Literal["live", "testnet",
                             "follow_execution"] = Field(...)


class TradingRiskManagementConfig(BaseModel):
    """Trading-level risk management config (legacy location in trading.yaml)."""
    model_config = ConfigDict(extra='forbid')

    data_sources: RiskManagementDataSourcesConfig = Field(...)


# SCORCHED-EARTH-2026-01-27: LegacyLoggingConfig DELETED (zombie code, observability.yaml is SSOT)

class SystemConfig(BaseModel):
    """System configuration (framework-level)."""
    model_config = ConfigDict(extra='forbid')

    # SCORCHED-EARTH-2026-01-27: logging field DELETED (LegacyLoggingConfig zombie, observability.yaml is SSOT)
    market_data: Optional[SystemMarketDataConfig] = Field(
        ..., description='Market data system settings')

    # Startup Guard Configuration (TASK-EXF-WIRE-STARTUP-09)
    validate_instruments_on_startup: bool = Field(
        ..., description="Enable startup validation of instruments.yaml against exchange (fail-closed)"
    )
    warn_only_filters: bool = Field(
        ..., description="If True, log warnings instead of crashing on filter mismatch (Dev/Shadow only)"
    )
    debug_event_listener_enabled: bool = Field(
        ..., description=(
            "Enable debug event listener (EVT:MARKET_TICK_RECEIVED, EVT:FEATURES_CALCULATED, EVT:TICK_FEATURES_CALCULATED, etc.). "
            "DEV ONLY: do not enable in production (high-frequency logging)."
        ),
    )


class SystemRuntimeMeta(BaseModel):
    """Runtime metadata captured during config load."""

    model_config = ConfigDict(extra='forbid')

    config_name: Optional[str] = Field(
        ..., description='Identifier of the loaded config profile')
    config_dir: Optional[str] = Field(
        ..., description='Filesystem path of the config directory in use')


class SystemMetaConfig(BaseModel):
    """Service/runtime metadata preserved under a dedicated namespace."""

    model_config = ConfigDict(extra='forbid')

    system_config_version: Optional[str] = Field(...)
    regime_config_version: Optional[str] = Field(...)
    sequential_tests: Dict[str, Any] = Field(...)
    risk_core: Dict[str, Any] = Field(...)
    kelly: Dict[str, Any] = Field(...)
    calibrator: Dict[str, Any] = Field(...)
    hawkes: Dict[str, Any] = Field(...)
    # PURGE-DIRTY-DOZEN: Removed hotreload_whitelist (dead stub, hot-reload never implemented) - 2026-01-25
    hardening: Dict[str, Any] = Field(...)
    position_tracking: Dict[str, Any] = Field(...)
    runtime: Optional[SystemRuntimeMeta] = Field(default=None)


class AuroraConfig(BaseModel):
    """
    Root configuration model for AuroraTrader.

    This replaces the old dict-based AuroraConfig class with full type validation.
    Pydantic V2 validates on instantiation, raising ValidationError immediately if config is invalid.
    """
    model_config = ConfigDict(extra='forbid')

    # Core app configs
    trading_mode: str = Field(
        ..., description='Trading mode: testnet | production | live')
    trading: TradingConfig = Field(...)

    # Exchange/account/market configs
    binance_api: BinanceApiConfig = Field(...)

    # System configs
    system: SystemConfig = Field(...)
    system_meta: SystemMetaConfig = Field(...)
    ops: OpsConfig = Field(...)

    # Observability configs (CFG-OBS-001: Centralized logging/metrics/tracing)
    observability: ObservabilityConfig = Field(
        ..., description='Centralized observability config (logging, metrics, tracing)'
    )

    # NOTE: bridge config removed (BRIDGE-SUNSET-01)
    # AuroraBridge was removed; ExecPosFSM now handles TRADE_INTENT_PROPOSED directly.

    # Domain configs (New)
    domains: DomainsConfig = Field(
        ..., description='Domain-specific configurations')

    # Canonical instruments SSOT (config/aurora/instruments.yaml)
    instruments: Dict[str, InstrumentPrecisionSpec] = Field(
        ..., description='Canonical instrument precision map (symbol -> tick_size/step_size)')

    # Strategies registry SSOT (config/aurora/strategies.yaml)
    # CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION
    strategies_registry: Optional[StrategiesRegistryConfig] = Field(
        ..., description='Strategy assignments + arbitration config (from strategies.yaml)')

    # Canonical strategy policy namespace (SSOT: strategies/<id>.yaml)
    strategies: StrategiesConfig = Field(
        ..., description="Canonical strategies namespace (policy SSOT)")

    # App-specific overrides
    # TASK23.FIX.B: Legacy root aliases must NOT be required.
    # If provided explicitly, they act as overrides; otherwise they should not block startup.
    execution: Optional[ExecutionConfig] = Field(
        ..., description='Override trading.execution if set')
    brackets: Optional[BracketsConfig] = Field(...)
    trailing: Optional[TrailingDefaultsConfig] = Field(
        ..., description='Global trailing stop defaults')

    # Regime Detector Config (loaded from regime.yaml, Pydantic-validated)
    models: Optional[RegimeModelsConfig] = Field(
        ..., description='Regime detection models from regime.yaml')

    regime_shift_inception: Optional[RegimeShiftInceptionConfig] = Field(
        ..., description='PKG-3: Rescue-only micro-entry on first bar of regime shift'
    )

    # regime.yaml SSOT (top-level keys)
    # REG-FIX-01: BAR-ONLY SSOT - these fields are REQUIRED (no silent defaults)
    basis_tf_sec: int = Field(
        ..., description='Bar-only regime updates: only process FEATURES_CALCULATED with matching tf_sec. '
        'REQUIRED - missing value fails config load (fail-closed).'
    )
    uncertain_cutoff: float = Field(
        ..., ge=0.0, le=1.0,
        description='Min confidence to emit non-UNCERTAIN regime. Below this threshold, demote to UNCERTAIN. '
                    'REQUIRED - missing value fails config load (fail-closed).'
    )
    # DM-CRITICAL-PATCHES-02: Liveness guard factor
    liveness_factor: int = Field(
        ..., ge=1,
        description='If no regime heartbeat received within (basis_tf_sec * liveness_factor) seconds, '
                    'block trading. Default: 3 (i.e., 15 minutes for 5m basis).'
    )

    # WARMUP-SSOT: Extra bars imported above regime_detector_required_bars() for fetch gap tolerance.
    # Total startup import = regime_detector_required_bars() + basis_import_buffer.
    basis_import_buffer: int = Field(
        ..., ge=0,
        description=(
            'Extra basis bars imported above regime_detector_required_bars() to absorb Binance fetch gaps. '
            'Source: regime.yaml. Total import = regime_required + basis_import_buffer.'
        ),
    )

    # HYSTERESIS-SLOPE-GATE-01: Regime stability
    hysteresis_bars: int = Field(
        ..., ge=1, le=10,
        description='Number of consecutive bars to confirm regime change before switching stable_regime.'
    )

    # Volatility Slope Gate: block HIGH_VOL with dying momentum
    vol_slope_gate_enabled: bool = Field(
        ..., description='Enable vol_ratio slope gate to detect "dying storm" (HIGH_VOL with falling momentum).'
    )
    vol_slope_gate_eps: float = Field(
        ..., ge=-0.1, le=0.1,
        description='Slope threshold: if vol_ratio slope <= eps for confirm_bars, force UNCERTAIN.'
    )
    vol_slope_gate_confirm_bars: int = Field(
        ..., ge=1, le=5,
        description='Number of bars slope must stay below eps to trigger gate.'
    )

    # SCORCHED-EARTH-2026-01-27: hmm and features fields DELETED (zero runtime references, regime.yaml not read by code)
    # PURGE-DIRTY-DOZEN: Removed hotreload_whitelist (dead stub, hot-reload never implemented) - 2026-01-25

    # Phase 0.0: System Stress Guard (independent circuit-breaker overlay)
    # None = disabled (no system_stress section in YAML or explicit null).
    # When present, all sub-fields are validated even if enabled=false.
    system_stress: Optional[SystemStressConfig] = Field(
        ..., description='System-wide stress guard (NORMAL/STRESS/EXTREME). None = disabled.'
    )

    @field_validator('trading_mode')
    @classmethod
    def validate_trading_mode(cls, v: str) -> str:
        """Ensure trading_mode is one of the valid values."""
        allowed_modes = ("testnet", "production", "live",
                         "hybrid_live_data_testnet_exec", "backtest")
        if v not in allowed_modes:
            raise ValueError(
                f"trading_mode must be one of: {', '.join(allowed_modes)}. Got: {v}")
        return v

    @field_validator('trading')
    @classmethod
    def validate_trading_mode_consistency(cls, v: TradingConfig, info) -> TradingConfig:
        """Ensure trading.mode and trading_mode are consistent."""
        # Note: In Pydantic V2, we can check info.data for other fields
        if 'trading_mode' in info.data:
            if v.mode != info.data['trading_mode']:
                # Optionally sync them or raise an error
                v.mode = info.data['trading_mode']
        return v

    @model_validator(mode='after')
    def _backcompat_root_execution_alias(self) -> "AuroraConfig":
        """Back-compat: expose trading.execution at root execution if root is unset.

        This is a deterministic aliasing rule and must not be implemented via loader dict mutation.
        """
        if self.execution is None and getattr(self.trading, "execution", None) is not None:
            self.execution = self.trading.execution
        return self

    @model_validator(mode="after")
    def _fail_closed_validate_aurora_tpsl_ssot(self) -> "AuroraConfig":
        """
        Fail-closed: TP/SL parameters must come from YAML SSOT (strategies/aurora.yaml per-asset config).

        This prevents silent runtime fallbacks that can quantize DOGE to 0.10000/0.20000 when tick_size is wrong
        or when per-asset exit/take_profit config is missing.
        It also requires active Aurora LOW_VOL geometry to clear the downstream
        low_vol_cost_floor_gate RR floor before runtime.
        """
        # TP/SL placement preflight (A3): required in YAML, no defaults.
        exec_cfg = getattr(self.trading, "execution", None)
        backoff_ms = getattr(exec_cfg, "preflight_backoff_ms",
                             None) if exec_cfg is not None else None
        if not backoff_ms:
            raise ValueError(
                "trading.execution.preflight_backoff_ms is required (TP/SL preflight backoff); omit is forbidden."
            )
        try:
            backoff_ms_ints = [int(x) for x in backoff_ms]
        except Exception as e:
            raise ValueError(
                f"Invalid trading.execution.preflight_backoff_ms: {backoff_ms!r} ({e})")
        if any(x <= 0 for x in backoff_ms_ints):
            raise ValueError(
                f"trading.execution.preflight_backoff_ms must be positive ints, got: {backoff_ms_ints}"
            )

        # Collect symbols that have 'aurora' strategy assigned
        aurora_symbols: list[str] = []
        if self.strategies_registry is not None and isinstance(self.strategies_registry.assignments, dict):
            for sym, strategies in self.strategies_registry.assignments.items():
                # Only require aurora assets for symbols with 'aurora' in assignments
                if isinstance(strategies, list) and "aurora" in strategies:
                    aurora_symbols.append(str(sym))
        # Fallback: if no registry, check all instruments
        if not aurora_symbols and self.strategies_registry is None:
            aurora_symbols = [str(s) for s in self.instruments.keys()]

        aurora = getattr(self.strategies, "aurora", None)
        if not aurora_symbols:
            # No symbols assigned to aurora — skip TP/SL SSOT validation
            return self
        if aurora is None:
            raise ValueError(
                "strategies.aurora is required: TP/SL SSOT lives in config/aurora/strategies/aurora.yaml"
            )

        decision_making = getattr(self.domains, "decision_making", None)
        gate_cfg = getattr(decision_making, "low_vol_cost_floor_gate", None)
        gate_thresholds = (
            getattr(gate_cfg, "thresholds",
                    None) if gate_cfg is not None else None
        )
        if gate_thresholds is None or getattr(gate_thresholds, "min_rr", None) is None:
            raise ValueError(
                "domains.decision_making.low_vol_cost_floor_gate.thresholds.min_rr is "
                "required for Aurora LOW_VOL TP/SL validation"
            )
        low_vol_min_rr = float(gate_thresholds.min_rr)

        def _coerce_float(raw_value: Any) -> float | None:
            try:
                return float(raw_value)
            except (TypeError, ValueError):
                return None

        missing: list[str] = []
        for symbol in aurora_symbols:
            cfg = aurora.assets.get(symbol)
            if cfg is None:
                missing.append(
                    f"{symbol} missing strategies.aurora.assets.{symbol}")
                continue

            exit_cfg = cfg.exit
            if exit_cfg is None or exit_cfg.sl_pct is None:
                missing.append(
                    f"{symbol} missing strategies.aurora.assets.{symbol}.exit.sl_pct")
            else:
                try:
                    sl_pct = float(exit_cfg.sl_pct)
                    if not (0.0 < sl_pct < 1.0):
                        missing.append(
                            f"{symbol} invalid strategies.aurora.assets.{symbol}.exit.sl_pct={exit_cfg.sl_pct}"
                        )
                except (TypeError, ValueError):
                    missing.append(
                        f"{symbol} invalid strategies.aurora.assets.{symbol}.exit.sl_pct={exit_cfg.sl_pct}"
                    )

            tp_cfg = cfg.take_profit
            if tp_cfg is None or tp_cfg.tp_low_ratio is None:
                missing.append(
                    f"{symbol} missing strategies.aurora.assets.{symbol}.take_profit.tp_low_ratio")
            else:
                try:
                    tp_low = float(tp_cfg.tp_low_ratio)
                    if tp_low <= 0.0:
                        missing.append(
                            f"{symbol} invalid strategies.aurora.assets.{symbol}.take_profit.tp_low_ratio={tp_cfg.tp_low_ratio}"
                        )
                except (TypeError, ValueError):
                    missing.append(
                        f"{symbol} invalid strategies.aurora.assets.{symbol}.take_profit.tp_low_ratio={tp_cfg.tp_low_ratio}"
                    )

            if tp_cfg is not None and tp_cfg.partial_exit_pct is not None:
                try:
                    p = float(tp_cfg.partial_exit_pct)
                    if not (0.0 < p < 1.0):
                        missing.append(
                            f"{symbol} invalid strategies.aurora.assets.{symbol}.take_profit.partial_exit_pct={tp_cfg.partial_exit_pct}"
                        )
                except (TypeError, ValueError):
                    missing.append(
                        f"{symbol} invalid strategies.aurora.assets.{symbol}.take_profit.partial_exit_pct={tp_cfg.partial_exit_pct}"
                    )

            regime_tpsl = exit_cfg.regime_tpsl
            if regime_tpsl is None:
                missing.append(
                    f"{symbol} missing strategies.aurora.assets.{symbol}.exit.regime_tpsl")
                continue

            regime_mode = getattr(regime_tpsl, "mode", None)
            if regime_mode == "pct_mult":
                if tp_cfg is None or tp_cfg.tp_low_ratio is None:
                    continue

                tp_mult_map = dict(getattr(regime_tpsl, "tp_mult", None) or {})
                if "DEFAULT" not in tp_mult_map:
                    missing.append(
                        f"{symbol} missing strategies.aurora.assets.{symbol}.exit.regime_tpsl.tp_mult.DEFAULT")
                    continue

                tp_mult_source = (
                    "LOW_VOLATILITY" if "LOW_VOLATILITY" in tp_mult_map else "DEFAULT"
                )
                tp_low = _coerce_float(tp_cfg.tp_low_ratio)
                tp_mult = _coerce_float(tp_mult_map.get(tp_mult_source))
                min_tp_rr = _coerce_float(
                    getattr(regime_tpsl, "min_tp_rr", None))
                max_tp_rr = _coerce_float(
                    getattr(regime_tpsl, "max_tp_rr", None))
                if (
                    tp_low is None
                    or tp_mult is None
                    or min_tp_rr is None
                    or max_tp_rr is None
                ):
                    missing.append(
                        f"{symbol} invalid strategies.aurora.assets.{symbol}.exit.regime_tpsl.pct_mult geometry")
                    continue

                effective_rr = max(min_tp_rr, min(tp_low * tp_mult, max_tp_rr))
                if effective_rr < low_vol_min_rr:
                    missing.append(
                        f"{symbol} low-vol effective RR={effective_rr:.6f} below "
                        f"domains.decision_making.low_vol_cost_floor_gate.thresholds.min_rr={low_vol_min_rr:.6f} "
                        f"(strategies.aurora.assets.{symbol}.exit.regime_tpsl.tp_mult."
                        f"{tp_mult_source}={tp_mult}, take_profit.tp_low_ratio={tp_low}, "
                        f"min_tp_rr={min_tp_rr}, max_tp_rr={max_tp_rr})"
                    )
            elif regime_mode == "atr":
                rr_map = dict(getattr(regime_tpsl, "rr_by_regime", None) or {})
                if "DEFAULT" not in rr_map:
                    missing.append(
                        f"{symbol} missing strategies.aurora.assets.{symbol}.exit.regime_tpsl.rr_by_regime.DEFAULT")
                    continue

                rr_source = (
                    "LOW_VOLATILITY" if "LOW_VOLATILITY" in rr_map else "DEFAULT"
                )
                rr = _coerce_float(rr_map.get(rr_source))
                min_tp_rr = _coerce_float(
                    getattr(regime_tpsl, "min_tp_rr", None))
                max_tp_rr = _coerce_float(
                    getattr(regime_tpsl, "max_tp_rr", None))
                if rr is None or min_tp_rr is None or max_tp_rr is None:
                    missing.append(
                        f"{symbol} invalid strategies.aurora.assets.{symbol}.exit.regime_tpsl.atr geometry")
                    continue

                effective_rr = max(min_tp_rr, min(rr, max_tp_rr))
                if effective_rr < low_vol_min_rr:
                    missing.append(
                        f"{symbol} low-vol effective RR={effective_rr:.6f} below "
                        f"domains.decision_making.low_vol_cost_floor_gate.thresholds.min_rr={low_vol_min_rr:.6f} "
                        f"(strategies.aurora.assets.{symbol}.exit.regime_tpsl.rr_by_regime."
                        f"{rr_source}={rr}, min_tp_rr={min_tp_rr}, max_tp_rr={max_tp_rr})"
                    )
            else:
                missing.append(
                    f"{symbol} invalid strategies.aurora.assets.{symbol}.exit.regime_tpsl.mode={regime_mode!r}"
                )

        if missing:
            raise ValueError("TP/SL SSOT validation failed: " +
                             "; ".join(sorted(missing)))

        return self

    @model_validator(mode="after")
    def _validate_md_amr_assignments(self) -> "AuroraConfig":
        sr = getattr(self, "strategies_registry", None)
        assignments = getattr(sr, "assignments", {}) if sr is not None else {}
        assigned = sorted(
            str(symbol)
            for symbol, strategy_ids in (assignments.items() if isinstance(assignments, dict) else [])
            if isinstance(strategy_ids, list) and "md_amr" in strategy_ids
        )
        if not assigned:
            return self

        cfg = getattr(self.strategies, "md_amr", None)
        if cfg is None:
            raise ValueError("strategy_config_missing(md_amr)")
        if not bool(cfg.enabled):
            raise ValueError("md_amr enabled=false for assigned symbols")

        invalid: list[str] = []
        for symbol in assigned:
            if symbol not in self.instruments:
                invalid.append(f"{symbol}:instrument_missing")
                continue
            asset_cfg = cfg.assets.get(symbol) if isinstance(
                cfg.assets, dict) else None
            if asset_cfg is None:
                invalid.append(f"{symbol}:asset_missing")
                continue
            if not bool(asset_cfg.enabled):
                invalid.append(f"{symbol}:enabled=false")
            allowed_regimes = getattr(asset_cfg, "allowed_regimes", None)
            if not isinstance(allowed_regimes, list) or not any(str(x).strip() for x in allowed_regimes):
                invalid.append(f"{symbol}:allowed_regimes_missing")
            if getattr(asset_cfg, "exit", None) is None:
                invalid.append(f"{symbol}:exit_missing")
        if invalid:
            raise ValueError(
                "md_amr contract invalid for assigned symbols: " + ", ".join(sorted(invalid)))
        return self

    @model_validator(mode="after")
    def _validate_mean_reversion_assignments(self) -> "AuroraConfig":
        sr = getattr(self, "strategies_registry", None)
        assignments = getattr(sr, "assignments", {}) if sr is not None else {}
        assigned = sorted(
            str(symbol)
            for symbol, strategy_ids in (assignments.items() if isinstance(assignments, dict) else [])
            if isinstance(strategy_ids, list) and "mean_reversion" in strategy_ids
        )
        if not assigned:
            return self

        cfg = getattr(self.strategies, "mean_reversion", None)
        if cfg is None:
            raise ValueError("strategy_config_missing(mean_reversion)")
        if not bool(cfg.enabled):
            raise ValueError(
                "mean_reversion enabled=false for assigned symbols")

        invalid: list[str] = []
        for symbol in assigned:
            if symbol not in self.instruments:
                invalid.append(f"{symbol}:instrument_missing")
                continue
            asset_cfg = cfg.assets.get(symbol) if isinstance(
                cfg.assets, dict) else None
            if asset_cfg is None:
                invalid.append(f"{symbol}:asset_missing")
                continue
            if not bool(asset_cfg.enabled):
                invalid.append(f"{symbol}:enabled=false")
            allowed_regimes = getattr(asset_cfg, "allowed_regimes", None)
            if not isinstance(allowed_regimes, list) or not any(str(x).strip() for x in allowed_regimes):
                invalid.append(f"{symbol}:allowed_regimes_missing")
        if invalid:
            raise ValueError(
                "mean_reversion contract invalid for assigned symbols: " + ", ".join(sorted(invalid)))
        return self

    @model_validator(mode="after")
    def _validate_strategy_objective_regime_coverage(self) -> "AuroraConfig":
        sr = getattr(self, "strategies_registry", None)
        assignments = getattr(sr, "assignments", {}) if sr is not None else {}
        if not isinstance(assignments, dict) or not assignments:
            return self

        def _assigned_symbols(strategy_id: str) -> list[str]:
            return sorted(
                str(symbol)
                for symbol, strategy_ids in assignments.items()
                if isinstance(strategy_ids, list) and strategy_id in strategy_ids
            )

        def _non_empty_regimes(raw: Any) -> set[str]:
            if not isinstance(raw, list):
                return set()
            return {str(value).strip().upper() for value in raw if str(value).strip()}

        coverage_errors: list[str] = []

        aurora_cfg = getattr(self.strategies, "aurora", None)
        aurora_objective = getattr(
            aurora_cfg, "objective", None) if aurora_cfg is not None else None
        if aurora_cfg is not None and aurora_objective is not None and bool(aurora_objective.enabled):
            expected_regimes: set[str] = set()
            for symbol in _assigned_symbols("aurora"):
                asset_cfg = aurora_cfg.assets.get(symbol) if isinstance(
                    aurora_cfg.assets, dict) else None
                if asset_cfg is None or not bool(getattr(asset_cfg, "enabled", False)):
                    continue
                expected_regimes.update(_non_empty_regimes(
                    getattr(asset_cfg, "allowed_regimes", None)))
            missing = sorted(expected_regimes -
                             set(aurora_objective.regimes.keys()))
            if missing:
                coverage_errors.append(
                    f"aurora:missing_objective_regimes={','.join(missing)}")

        md_cfg = getattr(self.strategies, "md_amr", None)
        md_objective = getattr(md_cfg, "objective",
                               None) if md_cfg is not None else None
        if md_cfg is not None and md_objective is not None and bool(md_objective.enabled):
            expected_regimes = set()
            for symbol in _assigned_symbols("md_amr"):
                asset_cfg = md_cfg.assets.get(symbol) if isinstance(
                    md_cfg.assets, dict) else None
                if asset_cfg is None or not bool(getattr(asset_cfg, "enabled", False)):
                    continue
                expected_regimes.update(_non_empty_regimes(
                    getattr(asset_cfg, "allowed_regimes", None)))
            missing = sorted(expected_regimes -
                             set(md_objective.regimes.keys()))
            if missing:
                coverage_errors.append(
                    f"md_amr:missing_objective_regimes={','.join(missing)}")

        mr_cfg = getattr(self.strategies, "mean_reversion", None)
        mr_objective = getattr(mr_cfg, "objective",
                               None) if mr_cfg is not None else None
        if mr_cfg is not None and mr_objective is not None and bool(mr_objective.enabled):
            expected_regimes = set()
            for symbol in _assigned_symbols("mean_reversion"):
                asset_cfg = mr_cfg.assets.get(symbol) if isinstance(
                    mr_cfg.assets, dict) else None
                if asset_cfg is None or not bool(getattr(asset_cfg, "enabled", False)):
                    continue
                expected_regimes.update(_non_empty_regimes(
                    getattr(asset_cfg, "allowed_regimes", None)))
            missing = sorted(expected_regimes -
                             set(mr_objective.regimes.keys()))
            if missing:
                coverage_errors.append(
                    f"mean_reversion:missing_objective_regimes={','.join(missing)}")

        if coverage_errors:
            raise ValueError(
                "objective regime coverage invalid for assigned symbols: " +
                "; ".join(coverage_errors)
            )
        return self

    @model_validator(mode="after")
    def _validate_llm_strategy_contract(self) -> "AuroraConfig":
        llm_cfg = getattr(self.trading, "llm_orchestration", None)
        if llm_cfg is None or str(llm_cfg.mode) == "baseline":
            return self

        sr = getattr(self, "strategies_registry", None)
        assignments = getattr(sr, "assignments", {}) if sr is not None else {}
        llm_assigned_anywhere = any(
            isinstance(
                strategy_ids, list) and "llm_microstructure" in strategy_ids
            for strategy_ids in (assignments.values() if isinstance(assignments, dict) else [])
        )
        if not llm_assigned_anywhere:
            return self

        symbols_llm = [str(symbol).upper()
                       for symbol in (llm_cfg.symbols_llm or [])]
        if not symbols_llm:
            raise ValueError(
                "trading.llm_orchestration.symbols_llm must be non-empty when mode != baseline")

        strategy_cfg = getattr(self.strategies, "llm_microstructure", None)
        if strategy_cfg is None:
            raise ValueError("strategy_config_missing(llm_microstructure)")

        for symbol in symbols_llm:
            assigned_ids = assignments.get(
                symbol, []) if isinstance(assignments, dict) else []
            if "llm_microstructure" not in assigned_ids:
                raise ValueError(
                    f"llm_microstructure not assigned for symbol {symbol}")
        return self


# Convenience function for creating config from dict
def create_aurora_config(config_data: Any) -> AuroraConfig:
    """Create an AuroraConfig from a dictionary or existing model.

    In testing/migration mode, we use model_construct to allow partial configs.
    """
    if isinstance(config_data, AuroraConfig):
        return config_data

    if not isinstance(config_data, dict):
        # Handle SimpleNamespace or other attribute-based objects
        try:
            from types import SimpleNamespace
            if isinstance(config_data, SimpleNamespace):
                # Simple conversion for top-level
                config_data = vars(config_data)
            elif hasattr(config_data, "__dict__"):
                config_data = vars(config_data)
        except Exception:
            pass

    if not isinstance(config_data, dict):
        raise TypeError(
            f"create_aurora_config requires dict or AuroraConfig, got {type(config_data)}")

    return AuroraConfig.model_construct(**config_data)


# Backward-compat imports for tests/legacy modules
AuroraTradingConfig = TradingConfig
AuroraExposureConfig = ExposureConfig
