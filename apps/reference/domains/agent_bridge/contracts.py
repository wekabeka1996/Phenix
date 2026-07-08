from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


FreshnessStatus = Literal["fresh", "stale", "missing", "unknown"]
SourceOwnership = Literal[
    "direct_main_publication",
    "publication_relay",
    "runtime_publication",
    "runtime_object",
    "bounded_disk_fallback",
    "missing",
    "mixed",
]
WarningDisposition = Literal["would_block", "warning", "context_note", "unknown"]
InvariantStatus = Literal["ready", "degraded", "missing", "unknown"]
CapabilityEvidenceLevel = Literal[
    "runtime_owner", "configured_only", "exchange_confirmed", "unavailable"
]
FilterDiagnosticState = Literal[
    "exchange_confirmed",
    "configured_only",
    "stale_exchange_info",
    "parity_mismatch",
    "exchange_missing",
    "configured_missing",
    "unavailable",
]
FilterParitySeverity = Literal[
    "match",
    "minor_mismatch",
    "material_mismatch",
    "exchange_missing",
    "configured_missing",
    "stale_exchange_info",
]
FilterParityStatus = Literal[
    "match",
    "conservative_mismatch",
    "risky_mismatch",
    "missing",
    "stale",
    "unavailable",
]
FilterParityGovernanceSeverity = Literal["info", "warning", "critical", "unavailable"]
FilterCompatibilityAssessment = Literal[
    "exact_match",
    "compatible_conservative",
    "incompatible_or_looser",
    "not_assessable",
]
FilterParityAckStatus = Literal[
    "unacknowledged",
    "acknowledged_conservative",
    "acknowledged_requires_review",
    "rejected",
    "expired",
    "not_required",
]
OperatorAckValidationStatus = Literal[
    "not_required",
    "missing",
    "valid",
    "expired",
    "state_mismatch",
    "rejected",
    "invalid_file",
    "invalid_semantics",
]


class CardMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ts_ms: Optional[int] = None
    produced_ts_ms: int
    freshness: FreshnessStatus
    source_refs: List[str] = Field(default_factory=list, max_length=8)
    missing_fields: List[str] = Field(default_factory=list, max_length=24)
    diagnostics: List[str] = Field(default_factory=list, max_length=12)
    source_ownership: SourceOwnership = "missing"


class GlobalMarketCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: CardMeta
    symbols_requested: List[str]
    symbols_available: List[str]
    equity_usd: Optional[float] = None
    available_balance_usd: Optional[float] = None
    open_positions_usd: Optional[float] = None
    unrealized_pnl_usd: Optional[float] = None
    realized_pnl_usd: Optional[float] = None
    active_position_count: Optional[int] = None


class SymbolMarketCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: CardMeta
    symbol: str
    tf_sec: int
    close_price: Optional[float] = None
    volume: Optional[float] = None
    regime: Optional[str] = None
    regime_confidence: Optional[float] = None
    decision_score: Optional[float] = None


class FeatureSignalCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: CardMeta
    symbol: str
    momentum: Optional[float] = None
    volatility: Optional[float] = None
    trend_strength: Optional[float] = None
    order_flow_imbalance: Optional[float] = None
    liquidity_score: Optional[float] = None
    signal_side: Optional[str] = None
    signal_confidence: Optional[float] = None


class PositionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    lifecycle_id: Optional[str] = None
    side: Optional[str] = None
    state: Optional[str] = None
    qty: Optional[str] = None
    entry_price: Optional[str] = None
    mark_price: Optional[str] = None
    unrealized_pnl: Optional[str] = None
    sl_price: Optional[str] = None
    tp_price: Optional[str] = None
    bracket_status: Optional[str] = None


class PositionLifeCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: CardMeta
    positions: List[PositionSummary] = Field(default_factory=list, max_length=20)
    lifecycle_reconciliation_available: bool


class AdvisoryWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    disposition: WarningDisposition
    symbol: Optional[str] = None
    message: str
    source_ref: str
    source_ts_ms: Optional[int] = None


class BusinessWarningsCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: CardMeta
    policy: Literal["advisory_only"] = "advisory_only"
    warnings: List[AdvisoryWarning] = Field(default_factory=list, max_length=24)


class MechanicalInvariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: InvariantStatus
    detail: str
    evidence_source: Optional[str] = None
    source_ts_ms: Optional[int] = None
    raw_ref: Optional[str] = None


class ExecutionCapabilityDescriptorV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    symbol: Optional[str] = None
    status: InvariantStatus
    evidence_level: CapabilityEvidenceLevel
    owner: str
    source_ts_ms: Optional[int] = None
    detail: str
    constraints: Dict[str, Optional[str | bool | int | float]] = Field(
        default_factory=dict, max_length=16
    )
    raw_ref: Optional[str] = None
    missing_reason: Optional[str] = None
    diagnostic_state: Optional[FilterDiagnosticState] = None


class SymbolConstraintSummaryV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    status: InvariantStatus
    evidence_level: CapabilityEvidenceLevel
    filter_source: str
    source_ts_ms: Optional[int] = None
    freshness: FreshnessStatus
    tick_size: Optional[str] = None
    step_size: Optional[str] = None
    min_qty: Optional[str] = None
    min_notional: Optional[str] = None
    missing_fields: List[str] = Field(default_factory=list, max_length=8)
    parity: Optional[FilterParitySeverity] = None
    field_parity: Dict[str, str] = Field(default_factory=dict, max_length=4)
    exchange_values: Dict[str, Optional[str]] = Field(default_factory=dict, max_length=4)
    parity_ref: Optional[str] = None


class FilterParityAcknowledgementV0(BaseModel):
    """Full read-only parity governance record retained outside the packet."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    venue: str
    environment: str
    parity_status: FilterParityStatus
    severity: FilterParityGovernanceSeverity
    first_seen_ts_ms: int
    last_seen_ts_ms: int
    configured_values: Dict[str, Optional[str]] = Field(default_factory=dict, max_length=4)
    exchange_values: Dict[str, Optional[str]] = Field(default_factory=dict, max_length=4)
    difference_summary: List[str] = Field(default_factory=list, max_length=4)
    compatibility_assessment: FilterCompatibilityAssessment
    operator_ack_status: FilterParityAckStatus
    operator_ack_ts_ms: Optional[int] = None
    operator_ack_note: Optional[str] = Field(default=None, max_length=512)
    operator_ack_id: Optional[str] = Field(default=None, max_length=128)
    operator_id: Optional[str] = Field(default=None, max_length=128)
    operator_display_name: Optional[str] = Field(default=None, max_length=128)
    operator_ack_expires_ts_ms: Optional[int] = None
    operator_review_required_by_ts_ms: Optional[int] = None
    operator_ack_reason: Optional[str] = Field(default=None, max_length=512)
    operator_ack_validation_status: OperatorAckValidationStatus = "missing"
    operator_ack_invalid_reason: Optional[str] = Field(default=None, max_length=256)
    operator_ack_provenance_ref: Optional[str] = None
    operator_ack_file_hash: Optional[str] = Field(default=None, max_length=64)
    requires_yaml_review: bool
    requires_execution_block_before_authority: bool
    configured_metadata_ref: str
    exchange_metadata_ref: str
    state_ref: str
    raw_ref: str
    history_ref: str


class FilterParityAckSummaryV0(BaseModel):
    """Bounded AgentFeedPacket projection; full values stay behind refs."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    parity_status: FilterParityStatus
    severity: FilterParityGovernanceSeverity
    ack_status: FilterParityAckStatus
    operator_id: Optional[str] = Field(default=None, max_length=128)
    created_ts_ms: Optional[int] = None
    expires_ts_ms: Optional[int] = None
    state_ref: str
    validation_status: OperatorAckValidationStatus
    requires_review: bool
    compatibility_summary: FilterCompatibilityAssessment
    reason: Optional[str] = Field(default=None, max_length=160)
    provenance_ref: Optional[str] = None
    raw_ref: str
    history_ref: str


class ActionReviewScenarioMemoryV1(BaseModel):
    """Compact no-execution memory projection; the full review stays in JSONL."""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    revision: int = Field(ge=1)
    symbol: str
    proposed_action: Optional[str] = None
    execution_status: Optional[str] = None
    expected_scenarios: Optional[List[str]] = Field(default=None, max_length=3)
    realized_scenario: Optional[str] = None
    lesson: Optional[str] = Field(default=None, max_length=240)
    unresolved: bool
    packet_ref: Optional[str] = None
    review_ref: str


class ActionReviewMemorySummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["action-review-memory-summary/v1"] = "action-review-memory-summary/v1"
    latest_review_ids_by_symbol: Dict[str, str] = Field(default_factory=dict, max_length=12)
    latest_scenario_memory: List[ActionReviewScenarioMemoryV1] = Field(
        default_factory=list, max_length=12
    )
    unresolved_review_count: int = Field(ge=0)
    unresolved_by_symbol: Dict[str, int] = Field(default_factory=dict, max_length=12)
    scenario_memory_index_ref: Optional[str] = None
    raw_ledger_ref: str


class ExecutionReadinessSummaryV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: int = 0
    degraded: int = 0
    missing: int = 0
    unknown: int = 0
    reasons: List[str] = Field(default_factory=list, max_length=16)


class ExecutionReadinessSnapshotV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["execution-readiness/v0"] = "execution-readiness/v0"
    produced_ts_ms: int
    runtime_available: bool
    symbols: List[str]
    invariants: List[MechanicalInvariant]
    capability_descriptors: List[ExecutionCapabilityDescriptorV0] = Field(
        default_factory=list, max_length=24
    )
    constraint_summary: List[SymbolConstraintSummaryV0] = Field(
        default_factory=list, max_length=12
    )
    filter_parity_acknowledgements: List[FilterParityAcknowledgementV0] = Field(
        default_factory=list, max_length=12
    )
    readiness_summary: ExecutionReadinessSummaryV0 = Field(
        default_factory=ExecutionReadinessSummaryV0
    )


class ExecutionBodyCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: CardMeta
    mode: Optional[str] = None
    execution_available: bool
    invariants: List[MechanicalInvariant]
    capability_descriptors: List[ExecutionCapabilityDescriptorV0] = Field(
        default_factory=list, max_length=24
    )
    constraint_summary: List[SymbolConstraintSummaryV0] = Field(
        default_factory=list, max_length=12
    )
    filter_parity_acknowledgements: List[FilterParityAckSummaryV0] = Field(
        default_factory=list, max_length=12
    )
    readiness_summary: ExecutionReadinessSummaryV0 = Field(
        default_factory=ExecutionReadinessSummaryV0
    )
    readiness_reasons: List[str] = Field(default_factory=list, max_length=16)
    trace_ref: Optional[str] = None
    readiness_snapshot: Optional[ExecutionReadinessSnapshotV0] = None


class FreshnessSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fresh: int = 0
    stale: int = 0
    missing: int = 0
    unknown: int = 0


class PacketBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimated_tokens: int = 0
    payload_bytes: int = 0
    max_tokens_requested: int
    truncated: bool = False
    omitted_sections: List[str] = Field(default_factory=list)


class AgentFeedPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-feed/v0"] = "agent-feed/v0"
    packet_id: str
    produced_ts_ms: int
    read_only: Literal[True] = True
    symbols: List[str]
    global_market: GlobalMarketCard
    symbol_markets: List[SymbolMarketCard]
    feature_signals: List[FeatureSignalCard]
    position_life: PositionLifeCard
    business_warnings: BusinessWarningsCard
    execution_body: ExecutionBodyCard
    action_review_memory: ActionReviewMemorySummaryV1
    budget: PacketBudget
    oldest_source_age_ms: Optional[int] = None
    freshness_summary: FreshnessSummary
    raw_refs: List[str] = Field(default_factory=list, max_length=32)
    diagnostics: List[str] = Field(default_factory=list, max_length=24)
    reducer_timings_ms: Dict[str, float] = Field(default_factory=dict)


class DirectionImpulseFeaturesV0(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delta_price: Optional[float] = None
    ema_bias: Optional[float] = None
    tfi: Optional[float] = None
    price_momentum_5m: Optional[float] = None
    macd_signal: Optional[float] = None


class ExhaustionLateEntryFeaturesV0(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rsi_14: Optional[float] = None
    bb_position: Optional[float] = None
    stoch_k: Optional[float] = None
    volume_zscore: Optional[float] = None
    volume_spike: Optional[float] = None


class LiquidityMicrostructureFeaturesV0(BaseModel):
    model_config = ConfigDict(extra="forbid")
    obi: Optional[float] = None
    depth_imbalance: Optional[float] = None
    liquidity_kappa: Optional[float] = None
    spread_bps: Optional[float] = None
    large_trade_imbalance: Optional[float] = None


class VolatilityCostFeaturesV0(BaseModel):
    model_config = ConfigDict(extra="forbid")
    volatility_state: Optional[float] = None
    atr_14: Optional[float] = None
    atr_ratio: Optional[float] = None
    realized_volatility_1h: Optional[float] = None
    bb_width: Optional[float] = None


class RegimeStructureFeaturesV0(BaseModel):
    model_config = ConfigDict(extra="forbid")
    macro_sync: Optional[float] = None
    pillar_sum: Optional[float] = None
    price_sma_20_deviation: Optional[float] = None
    price_range_ratio: Optional[float] = None


class PublishedFeatureFamiliesV0(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direction_impulse: DirectionImpulseFeaturesV0
    exhaustion_late_entry: ExhaustionLateEntryFeaturesV0
    liquidity_microstructure: LiquidityMicrostructureFeaturesV0
    volatility_cost_viability: VolatilityCostFeaturesV0
    regime_structure: RegimeStructureFeaturesV0


class PublishedMarketSymbolV0(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str
    tf_sec: int
    source_ts_ms: int
    bar_close_ts_ms: int
    feature_ts_ms: int
    last_price: Optional[float] = None
    regime_label: Optional[str] = None
    regime_confidence: Optional[float] = None
    feature_freshness: FreshnessStatus
    features: PublishedFeatureFamiliesV0
    missing_fields: List[str] = Field(default_factory=list, max_length=32)
    source_owner: Literal["aurora_main_event_bus", "aurora_main_feature_mirror_relay"]
    raw_refs: List[str] = Field(default_factory=list, max_length=8)


class AgentMarketRuntimeSnapshotV0(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["agent-market-runtime/v0"] = "agent-market-runtime/v0"
    produced_ts_ms: int
    publisher_version: Literal["p3.v0", "p4.v0", "p5.v0", "p6.v0", "p7.v0", "p8.v0", "p9.v0"] = "p3.v0"
    publication_status: Literal["ready", "degraded", "missing"]
    symbols: List[PublishedMarketSymbolV0] = Field(default_factory=list, max_length=12)


class AgentExecutionReadinessPublicationV0(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["agent-execution-readiness-publication/v0"] = "agent-execution-readiness-publication/v0"
    produced_ts_ms: int
    publisher_version: Literal["p3.v0", "p4.v0", "p5.v0", "p6.v0", "p7.v0", "p8.v0", "p9.v0"] = "p3.v0"
    source_owner: Literal["aurora_main_execution_position", "publication_relay_no_runtime"]
    snapshot: ExecutionReadinessSnapshotV0


class AgentBridgePublicationIndexV0(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["agent-bridge-publication-index/v0"] = "agent-bridge-publication-index/v0"
    produced_ts_ms: int
    publisher_version: Literal["p3.v0", "p4.v0", "p5.v0", "p6.v0", "p7.v0", "p8.v0", "p9.v0"] = "p3.v0"
    source_owner: Literal["direct_main_publication", "publication_relay"] = "publication_relay"
    publication_status: Literal["ready", "degraded", "missing"]
    market_ref: str
    execution_readiness_ref: str
    symbols_covered: List[str] = Field(default_factory=list, max_length=12)


class SourceInventoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: str
    available: bool
    source_ref: str
    size_bytes: Optional[int] = None
    modified_ts_ms: Optional[int] = None
    read_policy: str


class AgentFeedHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "degraded"]
    service: Literal["aurora-agent-feed-v0"] = "aurora-agent-feed-v0"
    read_only: Literal[True] = True
    produced_ts_ms: int
    source_families_available: int
    source_families_total: int
    diagnostics: List[str] = Field(default_factory=list)


COMPACT_FEATURE_ALIASES: Dict[str, List[str]] = {
    "momentum": ["momentum", "rsi", "returns", "price_momentum", "price_momentum_5m", "delta_price", "ema_bias"],
    "volatility": ["volatility", "atr", "realized_volatility", "volatility_state", "atr_ratio", "realized_volatility_1h"],
    "trend_strength": ["trend_strength", "adx", "trend_score", "macro_sync", "pillar_sum"],
    "order_flow_imbalance": ["order_flow_imbalance", "obi", "imbalance"],
    "liquidity_score": ["liquidity_score", "liquidity", "depth_score", "liquidity_kappa", "depth_imbalance"],
}
