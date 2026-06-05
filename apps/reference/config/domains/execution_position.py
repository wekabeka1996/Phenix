from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from apps.reference.contracts.runtime_regime_layers import normalize_structural_regime_label


class ExposureGuardConfig(BaseModel):
    """Exposure guard configuration."""

    model_config = ConfigDict(extra='forbid')

    pending_ttl_sec: int = Field(...)
    post_fill_ttl_sec: int = Field(...)
    stale_ttl_sec: int = Field(...)
    max_equity_utilization_pct: float = Field(...)
    max_portfolio_fraction: float = Field(...)
    max_long_utilization_pct: float = Field(...)
    max_short_utilization_pct: float = Field(...)
    max_directional_ratio: float = Field(...)
    max_concentration_pct: float = Field(...)


class FsmOpenConfig(BaseModel):
    """FSM open configuration."""

    model_config = ConfigDict(extra='forbid')

    idempotency_window_sec: int = Field(...)


class OrderIndexConfig(BaseModel):
    """Order index configuration."""

    model_config = ConfigDict(extra='forbid')

    ttl_sec: int = Field(...)


class MetricsCollectorConfig(BaseModel):
    """Metrics collector configuration."""

    model_config = ConfigDict(extra='forbid')

    window_size_minutes: int = Field(...)
    recent_rejections_minutes: int = Field(...)


class IdempotentCancelConfig(BaseModel):
    """Idempotent cancel configuration."""

    model_config = ConfigDict(extra='forbid')

    max_retries: int = Field(...)


class ExecutionUtilsConfig(BaseModel):
    """Execution utilities configuration."""

    model_config = ConfigDict(extra='forbid')

    client_order_id_max_length: int = Field(...)
    basis_points_base: float = Field(...)


class InflightReconcileConfig(BaseModel):
    """In-flight order reconciliation configuration (ExecutionPosition domain)."""

    model_config = ConfigDict(extra='forbid')

    inflight_ttl_sec: int = Field(
        ..., description="TTL before reconciliation check (seconds)"
    )
    max_ttl_sec: int = Field(
        ..., description="Force-clear after this TTL (seconds)"
    )
    reconcile_interval_sec: int = Field(
        ..., description="Interval between reconcile attempts (seconds)"
    )
    verbose_logging: bool = Field(...,
                                  description="Log reconciliation details")


class EventDedupConfig(BaseModel):
    """FSM event deduplication configuration (bounded memory)."""

    model_config = ConfigDict(extra='forbid')

    max_size: int = Field(
        ..., description="Max number of events to track"
    )
    ttl_ms: int = Field(
        ..., description="Event TTL in milliseconds (24h)"
    )
    warm_state: "EventDedupWarmStateConfig" = Field(
        ..., description="Legacy config key for cache-only restart seed persistence of recent exact terminal fill identities",
    )


class EventDedupWarmStateConfig(BaseModel):
    """Legacy-named cache-only configuration for exact terminal fill identity seeds."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable restart-seeded warm-state for exact terminal fill identity continuity",
    )
    storage_path: Optional[str] = Field(
        ..., description="Atomic JSON path for cache-only exact terminal fill identity seed persistence",
    )
    max_entries: int = Field(
        ..., description="Max exact terminal fill identities retained in warm-state snapshot",
    )


class DriftAwayConfig(BaseModel):
    """ADVANCED-STALE-CANCEL-01: Price drift threshold for evidence-based regime cancel."""

    model_config = ConfigDict(extra='forbid')

    mode: Literal["atr"] = Field(
        ..., description="Threshold mode. Supported: 'atr' (atr_14 * atr_mult).",
    )
    atr_mult: float = Field(
        ..., ge=0.01,
        le=10.0,
        description=(
            "Multiplier applied to atr_14. Cancel when "
            "|current_price - limit_price| > atr_14 * atr_mult."
        ),
    )


class AdvancedStaleCancelConfig(BaseModel):
    """Evidence-based pending entry cancel policy for regime changes."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable advanced stale cancel (overrides simple cancel_on_regime_change path)."
    )
    min_age_before_cancel_sec: int = Field(
        ..., ge=0,
        description="Order must be at least this old (seconds) before cancel is considered.",
    )
    drift_away: DriftAwayConfig = Field(
        ..., description="Price drift threshold configuration.",
    )
    may_cancel_regimes: Dict[str, List[str]] = Field(
        ..., description="Per-side regime labels that MAY cancel a pending entry for that side. Expected keys: BUY / SELL.",
    )
    never_cancel_regimes: List[str] = Field(
        ..., description="Regime labels that never trigger cancel.",
    )

    @model_validator(mode='after')
    def validate_regime_sets(self) -> 'AdvancedStaleCancelConfig':
        for side, regimes in self.may_cancel_regimes.items():
            if side not in ("BUY", "SELL"):
                raise ValueError(
                    f"may_cancel_regimes key must be 'BUY' or 'SELL', got '{side}'"
                )
            for regime in regimes:
                if str(regime).upper() == "UNCERTAIN":
                    raise ValueError(
                        "UNCERTAIN must not appear in may_cancel_regimes"
                    )
        return self


class SupersedeRepriceGuardConfig(BaseModel):
    """Guard against cancel/repost churn for same-side supersede replacements."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable supersede reprice guard analysis for same-side LIMIT replacements."
    )
    enforce: bool = Field(
        ..., description="If True, skip cancel/repost when price improvement is below threshold."
    )
    min_price_improvement_bps: float = Field(
        ..., ge=0.0,
        description="Minimum same-side price improvement in bps required to justify cancel/repost.",
    )
    min_price_improvement_atr_mult: float = Field(
        ..., ge=0.0,
        description="ATR-based minimum improvement multiplier. 0 disables ATR contribution.",
    )


class PendingEntryTTLConfig(BaseModel):
    """
    EP-01.3-INT: Per-timeframe TTL for pending LIMIT entry orders.

    When a LIMIT entry order is placed, we calculate valid_for_ms based on
    the strategy's timeframe (tf_sec). If the order is not filled within TTL,
    it is cancelled (no market fallback, no chase).

    Cancel triggers:
    - TTL expired: cancel via watchdog
    - Regime change: cancel if entry no longer valid for new regime
    - Supersede: cancel old pending if new open arrives for same symbol
    - Panic: cancel all pending on killswitch
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable per-timeframe pending entry TTL (if False, uses global watchdog fill_ttl_ms)"
    )
    ttl_by_tf_sec: Dict[int, int] = Field(
        ..., description=(
            "Map of timeframe_seconds -> entry_ttl_seconds. "
            "E.g. {180: 45, 300: 60, 900: 180} means 3m bars get 45s TTL, 5m get 60s, 15m get 180s."
        )
    )
    reject_unknown_tf: bool = Field(
        ..., description="If True (fail-closed), reject entry if tf_sec not in ttl_by_tf_sec map"
    )
    cancel_on_regime_change: bool = Field(
        ..., description="Cancel pending entry when EVT:REGIME_DETECTED indicates regime changed"
    )
    regime_change_cancel_mode: str = Field(
        ..., description=(
            "FIX-SOFT-CANCEL-01: How to handle pending orders on regime change. "
            "'immediate' = cancel at once (original). "
            "'let_ttl_expire' = skip cancel, let order live until TTL expires naturally. "
            "Only applies when cancel_on_regime_change=true."
        )
    )
    cancel_on_supersede: bool = Field(
        ..., description="Cancel old pending entry when new open request arrives for same symbol"
    )
    cancel_on_panic: bool = Field(
        ..., description="Cancel pending entry immediately when panic_killswitch is activated"
    )
    supersede_cancel_timeout_sec: float = Field(
        ...,
        ge=1.0,
        le=60.0,
        description="Timeout (seconds) to wait for supersede cancel confirmation before forcing new open. Explicit config required.",
    )
    supersede_reprice_guard: Optional[SupersedeRepriceGuardConfig] = Field(
        ..., description="Same-side LIMIT supersede churn guard.",
    )
    advanced_stale_cancel: Optional[AdvancedStaleCancelConfig] = Field(
        ..., description="Evidence-based stale cancel adapter for pending LIMIT entries.",
    )

    @model_validator(mode='after')
    def validate_ttl_values(self) -> 'PendingEntryTTLConfig':
        """Ensure all TTL values are positive and tf_sec >= 60."""
        for tf_sec, ttl_sec in self.ttl_by_tf_sec.items():
            if tf_sec < 60:
                raise ValueError(f"tf_sec must be >= 60, got {tf_sec}")
            if ttl_sec <= 0:
                raise ValueError(
                    f"TTL must be > 0, got {ttl_sec} for tf_sec={tf_sec}"
                )
        return self


class MakerOnlyEntryConfig(BaseModel):
    """
    EP-01.4-INT-B: Configuration for maker-only (post-only) entry orders.

    When enabled, LIMIT entry orders are placed with tif="GTX" (post-only).
    If the order would cross the book, it is rejected (MAKER_ONLY_REJECT).

    NO FALLBACK to market. NO retry with different tif.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable maker-only enforcement for entry LIMIT orders"
    )


class OrderCapabilitiesConfig(BaseModel):
    """ORDER-POLICY-01: Supported order types and TIF values for the execution layer.

    This is SSOT for what the system can process. Strategy policies must be
    a subset of these capabilities.
    """

    model_config = ConfigDict(extra='forbid')

    supported_order_types: List[Literal["LIMIT", "MARKET"]] = Field(
        ...,
        min_length=1,
        description="Allowed order types. No defaults - must be explicitly configured.",
    )
    supported_tif: List[Literal["GTC", "GTX", "IOC", "FOK"]] = Field(
        ...,
        min_length=1,
        description="Allowed time-in-force values. No defaults - must be explicitly configured.",
    )


class BracketPlacementConfig(BaseModel):
    """MAGIC-NUM-EXTRACTION: TP/SL bracket placement retry configuration.

    Extracted from hardcoded values in fsm.py for -2021 error handling
    (TP too close to mark price).

    Binance -2021 error: The stop price is too close to the mark price.
    Solution: Widen TP progressively with exponential backoff.
    """

    model_config = ConfigDict(extra='forbid')

    tp_widen_first_bps: int = Field(
        ..., ge=1,
        le=500,
        description="First retry: widen TP by N basis points (20 = 0.2%). Handles most -2021 cases.",
    )
    tp_widen_second_bps: int = Field(
        ..., ge=1,
        le=500,
        description="Second retry: widen TP by N basis points (50 = 0.5%). Handles volatile markets.",
    )
    retry_backoff_ms: List[int] = Field(
        ..., min_length=1,
        max_length=5,
        description="Backoff delays between retries (ms). [200, 400] = exponential backoff.",
    )


class OrderLifecycleConfig(BaseModel):
    """MAGIC-NUM-EXTRACTION: Order lifecycle timing configuration.

    Settlement delays are required because:
    - fill_settlement_delay_ms: REST API lag after MARKET fill before position updates
    - position_close_cleanup_delay_ms: Exchange-side settlement after CLOSE before orphan cleanup
    """

    model_config = ConfigDict(extra='forbid')

    fill_settlement_delay_ms: int = Field(
        ..., ge=100,
        le=5000,
        description="Delay after fill before bracket placement (REST API lag). 500ms typical for Binance Futures.",
    )
    position_close_cleanup_delay_ms: int = Field(
        ..., ge=500,
        le=10000,
        description="Delay after CLOSE before orphan bracket cleanup. Exchange-side settlement time.",
    )


class ShadowCheckConfig(BaseModel):
    """MAGIC-NUM-EXTRACTION: Shadow notional exposure check configuration.

    Periodic check comparing FSM-tracked exposure vs exchange-reported positions.
    Detects drift between internal state and exchange reality.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable periodic shadow exposure checks.",
    )
    check_every_n_requests: int = Field(
        ..., ge=1,
        le=100,
        description="Run shadow check every N exposure requests (sampling rate).",
    )
    tolerance_pct: float = Field(
        ..., ge=0.1,
        le=10.0,
        description="Allowed mismatch percentage before warning (1.0 = 1%).",
    )
    absolute_threshold_usd: float = Field(
        ..., ge=100.0,
        le=1000000.0,
        description="Absolute mismatch threshold in USD (for large portfolios).",
    )
    use_absolute_for_large_portfolios: bool = Field(
        ..., description="Use absolute threshold for portfolios above large_portfolio_threshold_usd.",
    )
    large_portfolio_threshold_usd: float = Field(
        ..., ge=10000.0,
        description="Portfolio value above which to use absolute threshold.",
    )


class GuardianConfig(BaseModel):
    """OrderGuardian configuration (already partially in use, completing extraction)."""

    model_config = ConfigDict(extra='forbid')

    @staticmethod
    def _coerce_tidy_bool(field_name: str, value: Any) -> bool:
        try:
            return TypeAdapter(bool).validate_python(value)
        except Exception as exc:
            raise ValueError(f"{field_name} must be boolean") from exc

    @model_validator(mode="before")
    @classmethod
    def resolve_tidy_monitoring_compat(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values

        has_legacy = "emit_tidy_event" in values
        has_monitoring = "emit_tidy_monitoring_event" in values
        if not has_legacy and not has_monitoring:
            return values

        updated = dict(values)
        legacy_value = None
        monitoring_value = None

        if has_legacy:
            legacy_value = cls._coerce_tidy_bool(
                "guardian.emit_tidy_event",
                values["emit_tidy_event"],
            )
            updated["emit_tidy_event"] = legacy_value

        if has_monitoring:
            monitoring_value = cls._coerce_tidy_bool(
                "guardian.emit_tidy_monitoring_event",
                values["emit_tidy_monitoring_event"],
            )
            updated["emit_tidy_monitoring_event"] = monitoring_value

        if has_legacy and has_monitoring and legacy_value != monitoring_value:
            raise ValueError(
                "guardian.emit_tidy_event and guardian.emit_tidy_monitoring_event differ; "
                "keep the deprecated compatibility field equal to the monitoring-only field"
            )

        resolved_value = monitoring_value if has_monitoring else legacy_value
        updated.setdefault("emit_tidy_event", resolved_value)
        updated.setdefault("emit_tidy_monitoring_event", resolved_value)
        return updated

    poll_interval_ms: int = Field(
        ...,
        ge=100,
        le=5000,
        description="Polling interval for OrderGuardian reconciliation loop.",
    )
    unified: bool = Field(
        ..., description="Use unified guardian mode (single reconcile loop for all symbols).",
    )
    emit_tidy_event: bool = Field(
        ...,
        description=(
            "Deprecated compatibility alias for emit_tidy_monitoring_event. "
            "Does not control EVT:SYMBOL_TIDY or entry-gate readiness."
        ),
    )
    emit_tidy_monitoring_event: bool = Field(
        ...,
        description=(
            "Emit monitoring EVT:EXECUTION_TIDY_PERFORMED after tidy operations. "
            "Does not control EVT:SYMBOL_TIDY or entry-gate readiness."
        ),
    )
    cleanup_ttl_ms: int = Field(
        ..., ge=1000,
        le=60000,
        description="TTL before considering an orphaned bracket for cleanup.",
    )
    symbol_cooldown_ms: int = Field(
        ..., ge=1000,
        le=60000,
        description="Cooldown after symbol tidy before next cleanup attempt.",
    )


class BracketHealthCheckConfig(BaseModel):
    """Periodic safety net for missing SL/TP brackets on open positions."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable periodic bracket health check loop."
    )
    interval_sec: int = Field(
        ...,
        ge=30,
        le=300,
        description="Seconds between health check cycles.",
    )
    grace_period_ms: int = Field(
        ...,
        ge=5000,
        description="Milliseconds after position open before checking brackets.",
    )
    max_placements_per_cycle: int = Field(
        ..., ge=1,
        le=10,
        description="Max bracket placements per cycle.",
    )


class IntentBoundaryAuditConfig(BaseModel):
    """Audit of TRADE_INTENT_PROPOSED progress across the execution boundary."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable background audit for TRADE_INTENT_PROPOSED routing.",
    )
    route_ttl_ms: int = Field(
        ..., ge=100,
        le=60000,
        description="Milliseconds allowed for a proposed intent to reach CMD:OPEN/CMD:CLOSE routing.",
    )
    downstream_ttl_ms: int = Field(
        ..., ge=100,
        le=120000,
        description="Milliseconds allowed after routing before a downstream execution event is observed.",
    )


class PositionPolicySidecarMode(str, Enum):
    """Operating mode for the bounded position policy sidecar."""

    DISABLE = "disable"
    SHADOW = "shadow"
    ENABLE = "enable"


_POSITION_POLICY_SIDECAR_CANONICAL_STRUCTURAL_REGIME_LABELS = frozenset(
    {
        "TREND_UP",
        "TREND_DOWN",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "MEAN_REVERSION",
        "UNCERTAIN",
    }
)


class PositionPolicySidecarFreshnessConfig(BaseModel):
    """Freshness requirements for sidecar evaluation inputs."""

    model_config = ConfigDict(extra='forbid')

    portfolio_max_age_ms: int = Field(..., ge=100, le=600000)
    features_max_age_ms: int = Field(..., ge=100, le=600000)
    regime_max_age_ms: int = Field(..., ge=100, le=600000)
    order_state_max_age_ms: int = Field(..., ge=100, le=600000)


class PositionPolicySidecarStartupGraceConfig(BaseModel):
    """Startup and post-fill grace windows for fail-closed evaluation."""

    model_config = ConfigDict(extra='forbid')

    startup_grace_ms: int = Field(..., ge=0, le=600000)
    post_fill_grace_ms: int = Field(..., ge=0, le=600000)
    min_portfolio_updates: int = Field(..., ge=1, le=10)
    min_feature_updates: int = Field(..., ge=1, le=10)
    min_regime_updates: int = Field(..., ge=1, le=10)


class PositionPolicySidecarProfitabilityGuardConfig(BaseModel):
    """Profitability guard for suppressing soft-loss recommendations."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    min_unrealized_pnl_pct: float = Field(..., ge=0.0)
    min_unrealized_pnl_usdt: float = Field(..., ge=0.0)


class PositionPolicySidecarScoringWeightsConfig(BaseModel):
    """Composite score weights."""

    model_config = ConfigDict(extra='forbid')

    microstructure_adverse_pressure: float = Field(..., ge=0.0, le=1.0)
    regime_exhaustion_hint: float = Field(..., ge=0.0, le=1.0)
    conviction_decay: float = Field(..., ge=0.0, le=1.0)
    unrealized_loss_pressure: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_non_zero_weight_sum(self) -> "PositionPolicySidecarScoringWeightsConfig":
        if (
            self.microstructure_adverse_pressure
            + self.regime_exhaustion_hint
            + self.conviction_decay
            + self.unrealized_loss_pressure
        ) <= 0.0:
            raise ValueError(
                "position_policy_sidecar.scoring.weights must sum to > 0"
            )
        return self


class PositionPolicySidecarScoringCapsConfig(BaseModel):
    """Per-component contribution caps."""

    model_config = ConfigDict(extra='forbid')

    microstructure_adverse_pressure: float = Field(..., ge=0.0, le=1.0)
    regime_exhaustion_hint: float = Field(..., ge=0.0, le=1.0)
    conviction_decay: float = Field(..., ge=0.0, le=1.0)
    unrealized_loss_pressure: float = Field(..., ge=0.0, le=1.0)


class PositionPolicySidecarScoringConfig(BaseModel):
    """Score composition configuration."""

    model_config = ConfigDict(extra='forbid')

    weights: PositionPolicySidecarScoringWeightsConfig = Field(...)
    caps: PositionPolicySidecarScoringCapsConfig = Field(...)


class PositionPolicySidecarThresholdsConfig(BaseModel):
    """Thresholds and label mappings used by the sidecar."""

    model_config = ConfigDict(extra='forbid')

    recommend_soft_close_at: float = Field(..., ge=0.0, le=1.0)
    loss_bps_full_pressure: float = Field(..., gt=0.0)
    adverse_price_distance_bps_full_pressure: float = Field(..., gt=0.0)
    book_imbalance_full_pressure: float = Field(..., gt=0.0, le=1.0)
    regime_confidence_floor: float = Field(..., gt=0.0, le=1.0)
    signal_score_floor: float = Field(...)
    adverse_regimes_long: List[str] = Field(..., min_length=1)
    adverse_regimes_short: List[str] = Field(..., min_length=1)

    @field_validator("adverse_regimes_long", "adverse_regimes_short")
    @classmethod
    def _normalize_regime_labels(cls, value: List[str]) -> List[str]:
        normalized: List[str] = []
        for item in value:
            label = str(item).strip()
            if not label:
                raise ValueError("regime labels must be non-empty")
            normalized_label = normalize_structural_regime_label(label)
            if normalized_label.startswith("FLAT_"):
                raise ValueError(
                    f"unsupported sidecar regime label {label!r}: strategy-local flat buckets are not allowed"
                )
            if normalized_label not in _POSITION_POLICY_SIDECAR_CANONICAL_STRUCTURAL_REGIME_LABELS:
                supported = ", ".join(
                    sorted(
                        _POSITION_POLICY_SIDECAR_CANONICAL_STRUCTURAL_REGIME_LABELS)
                )
                raise ValueError(
                    f"unsupported sidecar regime label {label!r}: use canonical structural labels only ({supported})"
                )
            normalized.append(normalized_label)
        return normalized


class PositionPolicySidecarLoggingConfig(BaseModel):
    """Logging and forensic output switches."""

    model_config = ConfigDict(extra='forbid')

    emit_internal_bus_events: bool = Field(...)
    write_trade_lifecycle_jsonl: bool = Field(...)
    trade_lifecycle_log_path: str = Field(..., min_length=1)
    include_score_payloads: bool = Field(...)


class PositionPolicySidecarAllowedActionsConfig(BaseModel):
    """Declared bounded action scope for the sidecar contract."""

    model_config = ConfigDict(extra='forbid')

    soft_close_symbol_current_net_only: bool = Field(...)
    partial_reduce: bool = Field(...)
    bracket_mutation: bool = Field(...)
    exact_targeting: bool = Field(...)


class PositionPolicySidecarPeakGivebackConfig(BaseModel):
    """Peak-giveback close trigger configuration."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    edge_arm_usd: float = Field(..., ge=0.0)
    giveback_trigger_pct: float = Field(..., ge=0.0, le=100.0)


class PositionPolicySidecarShadowPercentNotionalArmConfig(BaseModel):
    """Shadow-only percent-of-notional arming candidates (percent units, not ratio)."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    candidate_pcts: List[float] = Field(..., min_length=1)

    @field_validator("candidate_pcts")
    @classmethod
    def _validate_candidate_pcts(cls, value: List[float]) -> List[float]:
        validated: List[float] = []
        for candidate in value:
            candidate_pct = float(candidate)
            if candidate_pct <= 0.0:
                raise ValueError(
                    "shadow_percent_notional_arm.candidate_pcts must contain only positive percent values"
                )
            validated.append(candidate_pct)
        return validated


class PositionPolicySidecarShadowFeeAwareArmFeeSource(str, Enum):
    """Supported fee source labels for shadow fee-aware arming."""

    REALIZED_LIFECYCLE_FEE = "realized_lifecycle_fee"
    ORDER_LOG_FEE = "order_log_fee"
    CONFIGURED_FEE_MODEL = "configured_fee_model"


class PositionPolicySidecarShadowFeeAwareConfiguredFeeModelConfig(BaseModel):
    """Explicit fallback fee model used only when enabled in config."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    round_trip_fee_bps: Optional[float] = Field(...)

    @model_validator(mode="after")
    def _validate_round_trip_fee_bps(
        self,
    ) -> "PositionPolicySidecarShadowFeeAwareConfiguredFeeModelConfig":
        if self.enabled and self.round_trip_fee_bps is None:
            raise ValueError(
                "shadow_fee_aware_arm.configured_fee_model.round_trip_fee_bps is required when enabled"
            )
        if self.round_trip_fee_bps is not None and float(self.round_trip_fee_bps) <= 0.0:
            raise ValueError(
                "shadow_fee_aware_arm.configured_fee_model.round_trip_fee_bps must be positive when provided"
            )
        return self


class PositionPolicySidecarShadowFeeAwareOptionalPctFloorConfig(BaseModel):
    """Optional percent-of-notional floor candidates (percent units, not ratio)."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    candidate_pcts: List[float] = Field(..., min_length=1)

    @field_validator("candidate_pcts")
    @classmethod
    def _validate_candidate_pcts(cls, value: List[float]) -> List[float]:
        validated: List[float] = []
        for candidate in value:
            candidate_pct = float(candidate)
            if candidate_pct <= 0.0:
                raise ValueError(
                    "shadow_fee_aware_arm.optional_pct_notional_floor.candidate_pcts must contain only positive percent values"
                )
            validated.append(candidate_pct)
        return validated


class PositionPolicySidecarShadowFeeAwareArmConfig(BaseModel):
    """Shadow-only fee-aware arm telemetry configuration."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    fee_source_priority: List[PositionPolicySidecarShadowFeeAwareArmFeeSource] = Field(
        ..., min_length=1
    )
    candidate_fee_multiples: List[float] = Field(..., min_length=1)
    configured_fee_model: PositionPolicySidecarShadowFeeAwareConfiguredFeeModelConfig = Field(
        ...
    )
    optional_pct_notional_floor: PositionPolicySidecarShadowFeeAwareOptionalPctFloorConfig = Field(
        ...
    )

    @field_validator("candidate_fee_multiples")
    @classmethod
    def _validate_candidate_fee_multiples(cls, value: List[float]) -> List[float]:
        validated: List[float] = []
        for candidate in value:
            candidate_multiple = float(candidate)
            if candidate_multiple <= 0.0:
                raise ValueError(
                    "shadow_fee_aware_arm.candidate_fee_multiples must contain only positive unitless multipliers"
                )
            validated.append(candidate_multiple)
        return validated


class PositionPolicySidecarConfig(BaseModel):
    """Strict configuration contract for the position policy sidecar."""

    model_config = ConfigDict(extra='forbid')

    mode: PositionPolicySidecarMode = Field(...)
    freshness: PositionPolicySidecarFreshnessConfig = Field(...)
    startup_grace: PositionPolicySidecarStartupGraceConfig = Field(...)
    profitability_guard: PositionPolicySidecarProfitabilityGuardConfig = Field(
        ...)
    scoring: PositionPolicySidecarScoringConfig = Field(...)
    thresholds: PositionPolicySidecarThresholdsConfig = Field(...)
    logging: PositionPolicySidecarLoggingConfig = Field(...)
    allowed_actions: PositionPolicySidecarAllowedActionsConfig = Field(...)
    peak_giveback_close: PositionPolicySidecarPeakGivebackConfig = Field(...)
    shadow_percent_notional_arm: PositionPolicySidecarShadowPercentNotionalArmConfig = Field(
        ...
    )
    shadow_fee_aware_arm: PositionPolicySidecarShadowFeeAwareArmConfig = Field(
        ...)

    @model_validator(mode="after")
    def _validate_bounded_action_scope(self) -> "PositionPolicySidecarConfig":
        if self.allowed_actions.partial_reduce:
            raise ValueError(
                "Bounded position_policy_sidecar contract forbids partial_reduce"
            )
        if self.allowed_actions.bracket_mutation:
            raise ValueError(
                "Bounded position_policy_sidecar contract forbids bracket_mutation"
            )
        if self.allowed_actions.exact_targeting:
            raise ValueError(
                "Bounded position_policy_sidecar contract forbids exact_targeting"
            )
        return self


class ExecutionPositionRestoreArtifactMode(str, Enum):
    """Writer/read rollout mode for the execution restore artifact."""

    OFF = "off"
    WRITER_ONLY = "writer_only"
    DARK_READ = "dark_read"
    AUTHORITATIVE = "authoritative"


class ExecutionPositionRestoreArtifactConfig(BaseModel):
    """Strict SSOT for the execution restore artifact rollout surface."""

    model_config = ConfigDict(extra='forbid')

    mode: ExecutionPositionRestoreArtifactMode = Field(
        ..., description="Restore artifact rollout mode."
    )
    storage_path: str = Field(
        ..., min_length=1,
        description="Canonical whole-envelope JSON path for execution restore persistence.",
    )
    flush_interval_ms: int = Field(
        ..., gt=0,
        description="Bounded periodic flush interval while active restore state exists.",
    )
    dark_read_max_artifact_age_ms: Optional[int] = Field(
        ..., gt=0,
        description="Optional stale-age threshold for startup dark-read comparisons.",
    )


class ExecutionPositionStartupTruthArtifactMode(str, Enum):
    """Writer rollout mode for the dedicated execution startup truth artifact."""

    OFF = "off"
    WRITER_ONLY = "writer_only"


class ExecutionPositionStartupTruthArtifactConfig(BaseModel):
    """Strict SSOT for the dedicated execution startup truth artifact."""

    model_config = ConfigDict(extra='forbid')

    mode: ExecutionPositionStartupTruthArtifactMode = Field(
        ..., description="Dedicated startup truth artifact rollout mode."
    )
    storage_path: str = Field(
        ..., min_length=1,
        description="Canonical append-only JSONL path for execution startup truth summaries.",
    )


class ExecutionPositionDomainConfig(BaseModel):
    """Complete execution position domain configuration."""

    model_config = ConfigDict(extra='forbid')

    fallback: FallbackConfig = Field(
        ..., description="Explicit fail-closed fallback policy."
    )
    exposure_guard: ExposureGuardConfig = Field(...)
    fsm_open: FsmOpenConfig = Field(...)
    order_index: OrderIndexConfig = Field(...)
    inflight_reconcile: InflightReconcileConfig = Field(...)
    metrics_collector: MetricsCollectorConfig = Field(...)
    idempotent_cancel: IdempotentCancelConfig = Field(...)
    utils: ExecutionUtilsConfig = Field(...)
    event_dedup: Optional[EventDedupConfig] = Field(
        ..., description="Event deduplication config"
    )
    pending_entry_ttl: PendingEntryTTLConfig = Field(
        ..., description="EP-01.3: Per-timeframe TTL for pending LIMIT entry orders"
    )
    maker_only_entry: MakerOnlyEntryConfig = Field(
        ..., description="EP-01.4: Maker-only (GTX) entry order configuration",
    )
    order_capabilities: OrderCapabilitiesConfig = Field(
        ..., description="ORDER-POLICY-01: Supported order types and TIF for the exchange adapter"
    )
    bracket_placement: BracketPlacementConfig = Field(
        ..., description="TP/SL bracket placement retry config for -2021 error handling",
    )
    order_lifecycle: OrderLifecycleConfig = Field(
        ..., description="Settlement delays and preflight timing for order lifecycle",
    )
    shadow_check: ShadowCheckConfig = Field(
        ..., description="Periodic shadow notional exposure validation",
    )
    guardian: GuardianConfig = Field(
        ..., description="OrderGuardian polling and cleanup configuration",
    )
    intent_boundary_audit: IntentBoundaryAuditConfig = Field(
        ..., description="Audit config for the TRADE_INTENT_PROPOSED -> execution boundary",
    )
    bracket_health_check: Optional[BracketHealthCheckConfig] = Field(
        ..., description="Current-native adapter config for bracket health reconciliation.",
    )
    restore_artifact: ExecutionPositionRestoreArtifactConfig = Field(
        ..., description="Writer/read rollout config for the canonical execution restore artifact."
    )
    startup_truth_artifact: ExecutionPositionStartupTruthArtifactConfig = Field(
        ..., description="Writer rollout config for the dedicated execution startup truth artifact."
    )
    position_policy_sidecar: PositionPolicySidecarConfig = Field(
        ..., description="Position Policy Sidecar typed config for open-position recommendation logic."
    )
    trade_executed_cutover_active: bool = Field(
        default=False,
        description="Phase 10: Enable formal authoritative state mutation for TRADE_EXECUTED terminal truth contour."
    )
