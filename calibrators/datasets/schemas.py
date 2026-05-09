"""Canonical dataset schema models (Pydantic v2).

These are OFFLINE calibration contracts, not runtime event schemas.
Each row type represents a single record in a calibration dataset.

No runtime code should import these models.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class CalibrationMarketBarRowV1(BaseModel):
    """Raw market bar row from recorder.

    Quality Level: RAW_RUNTIME
    Primary Purpose: Store recorder bar data with minimal transformation.
    """

    dataset_schema: Literal["calibration_market_bar_dataset_v1"]
    dataset_version: str = Field(description="Schema version, e.g., '1.0.0'")
    source_surface: str = Field(
        description="e.g., 'recorder_csv', 'binance_kline'")
    source_file: str = Field(description="Absolute or relative file path")
    session_date: str | None = Field(
        default=None, description="YYYY-MM-DD if known, else None"
    )
    symbol: str = Field(description="e.g., 'BTCUSDT'")
    tf_sec: int = Field(description="Timeframe in seconds, e.g., 300")
    ts_ms: int = Field(description="Timestamp in milliseconds (wallclock)")
    bar_close_ts_ms: int | None = Field(
        default=None, description="Bar close timestamp if different from ts_ms"
    )
    open: float
    high: float
    low: float
    close: float
    volume: float | None = Field(
        default=None, description="Quote volume or None")
    trade_count: int | None = Field(
        default=None, description="Number of trades or None")
    data_quality: str = Field(
        description="'good', 'stale', 'missing', 'malformed'")
    synthetic: bool = Field(
        default=False, description="True if row is synthetic/test, False if runtime-derived"
    )

    model_config = {"extra": "forbid"}


class CalibrationFeatureSnapshotRowV1(BaseModel):
    """Feature vector snapshot at a point in time.

    Quality Level: JOINED_RUNTIME
    Primary Purpose: Store computed feature state with readiness metadata.
    """

    dataset_schema: Literal["calibration_feature_snapshot_dataset_v1"]
    dataset_version: str
    source_surface: str = Field(
        description="e.g., 'ta_features_log', 'logs/features'")
    source_file: str
    symbol: str
    tf_sec: int
    ts_ms: int = Field(description="Feature snapshot timestamp (ms)")
    close: float = Field(description="Close price at snapshot time")
    features: dict[str, float | int | str | bool | None] = Field(
        description="Feature name -> value mapping; None for missing"
    )
    feature_version: str | None = Field(
        default=None, description="Version of feature set, e.g., 'v2.1.0'"
    )
    ready: bool | None = Field(
        default=None, description="True if all features ready, False if degraded, None if unknown"
    )
    not_ready_reasons: list[str] = Field(
        default_factory=list, description="List of reason codes if ready=False"
    )
    regime: str | None = Field(
        default=None, description="Regime label at snapshot time")
    regime_confidence: float | None = Field(
        default=None, description="Regime confidence 0..1 or None"
    )
    missingness_mask: dict[str, bool] = Field(
        description="Feature name -> True if missing, False if present"
    )
    freshness_ms: int | None = Field(
        default=None,
        description="How stale the snapshot is relative to ts_ms, or None",
    )
    synthetic: bool = False

    model_config = {"extra": "forbid"}


class CalibrationOracleRegimeLabelRowV1(BaseModel):
    """Labelled regime row with forward-looking oracle label.

    Quality Level: DERIVED_LABELLED
    Primary Purpose: Training input for regime models; labels are computed forward.
    """

    dataset_schema: Literal["calibration_oracle_regime_labels_v1"]
    dataset_version: str
    source_dataset_id: str = Field(
        description="e.g., 'calibration_market_bar_dataset_v1'")
    symbol: str
    tf_sec: int
    ts_ms: int = Field(description="Label observation time")
    horizon_bars: int = Field(
        description="Number of bars ahead for label horizon")
    future_return_bps: float = Field(
        description="Return over horizon in basis points")
    future_volatility_bps: float = Field(
        description="Realized volatility over horizon in bps"
    )
    flip_rate: float = Field(
        description="Proportion of horizon bars that saw direction reversal"
    )
    oracle_regime: str = Field(
        description="Label target, e.g., 'up', 'down', 'ranging'")
    label_version: str = Field(description="Label algorithm version")
    split_bucket: str = Field(
        description="'train', 'validation', or 'forward' split assignment"
    )
    synthetic: bool = False

    model_config = {"extra": "forbid"}


class CalibrationTradeDecisionRowV1(BaseModel):
    """Decision/intent capture from authority journals or direct decision log.

    Quality Level: JOINED_RUNTIME
    Primary Purpose: Store decision context for outcome join.
    """

    dataset_schema: Literal["calibration_trade_decision_dataset_v1"]
    dataset_version: str
    decision_id: str | None = Field(
        default=None, description="Unique decision ID or None if diagnostics-only"
    )
    rid: str | None = Field(
        default=None, description="Request ID from authority bridge or None"
    )
    symbol: str
    strategy_id: str | None = Field(
        default=None, description="Strategy name or None")
    side: str | None = Field(
        default=None, description="'long', 'short', or None")
    proposed_action: str | None = Field(
        default=None, description="Proposed action code or None"
    )
    decision_basis_ts_ms: int | None = Field(
        default=None, description="Timestamp of decision input state (causal)"
    )
    request_ts_ms: int | None = Field(
        default=None, description="Authority request time (causal)"
    )
    response_ts_ms: int | None = Field(
        default=None, description="Authority response time (causal)"
    )
    authority_mode: str | None = Field(
        default=None, description="Authority mode (e.g., 'live', 'shadow')"
    )
    action: str | None = Field(
        default=None, description="Actual action taken or None"
    )
    apply_result: str | None = Field(
        default=None, description="Application outcome ('accepted', 'rejected', etc.)"
    )
    reason_code: str | None = Field(
        default=None, description="Reason code if rejected"
    )
    dataset_visibility: str = Field(
        description="'causal_complete', 'diagnostics_only', or 'uncertain'"
    )
    observation_causal: bool = Field(
        description="True if observation is causal (no lookahead), False if synthetic"
    )
    source_paths: list[str] = Field(
        default_factory=list, description="Source files or journal paths"
    )
    synthetic: bool = False

    model_config = {"extra": "forbid"}


class CalibrationRealizedTradeRowV1(BaseModel):
    """Realized trade outcome join across decision, execution, and settlement.

    Quality Level: DERIVED_LABELLED
    Primary Purpose: Training target for entry/exit calibration.
    """

    dataset_schema: Literal["calibration_realized_trade_dataset_v1"]
    dataset_version: str
    attempt_id: str | None = Field(
        default=None, description="Entry attempt ID or None"
    )
    decision_id: str | None = Field(
        default=None, description="Decision ID or None"
    )
    rid: str | None = Field(
        default=None, description="Request ID or None"
    )
    lifecycle_id: str | None = Field(
        default=None, description="Trade lifecycle ID or None"
    )
    symbol: str
    strategy_id: str | None = Field(
        default=None, description="Strategy name or None")
    side: str
    intent_ts_ms: int | None = Field(
        default=None, description="Intent timestamp"
    )
    entry_ts_ms: int | None = Field(
        default=None, description="Entry/fill timestamp"
    )
    exit_ts_ms: int | None = Field(
        default=None, description="Exit/close timestamp"
    )
    entry_price: float | None = Field(
        default=None, description="Entry fill price")
    exit_price: float | None = Field(
        default=None, description="Exit fill price")
    qty: float | None = Field(default=None, description="Position quantity")
    outcome: str | None = Field(
        default=None, description="'closed_win', 'closed_loss', 'open', 'cancelled'"
    )
    gross_pnl: float | None = Field(
        default=None, description="PnL before fees")
    realized_pnl_net: float | None = Field(
        default=None, description="PnL after fees")
    fees: float | None = Field(default=None, description="Total fees paid")
    commission: float | None = Field(
        default=None, description="Commission cost")
    mfe: float | None = Field(
        default=None, description="Maximum Favorable Excursion in bps"
    )
    mae: float | None = Field(
        default=None, description="Maximum Adverse Excursion in bps"
    )
    bars_held: int | None = Field(
        default=None, description="Number of bars from entry to exit"
    )
    exact_roundtrip: bool = Field(
        description="True if entry and exit were both captured; False if partial"
    )
    terminal_status: str | None = Field(
        default=None, description="Terminal status code"
    )
    source_paths: list[str] = Field(
        default_factory=list, description="Source files or ledger paths"
    )
    synthetic: bool = False

    model_config = {"extra": "forbid"}


class CalibrationLowVolGateRowV1(BaseModel):
    """Low volatility gate outcome row (nrr062, low_vol_cost_floor).

    Quality Level: DERIVED_LABELLED
    Primary Purpose: Gate decision calibration for low-vol regime.
    """

    dataset_schema: Literal["calibration_low_vol_gate_dataset_v1"]
    dataset_version: str
    attempt_id: str | None = Field(default=None)
    decision_id: str | None = Field(default=None)
    symbol: str
    strategy_id: str | None = Field(default=None)
    side: str | None = Field(default=None)
    regime: str | None = Field(
        default=None, description="Regime at decision time")
    regime_confidence: float | None = Field(default=None)
    direction_confidence: float | None = Field(default=None)
    target_net_fee_multiple: float | None = Field(
        default=None, description="Required return as multiple of fees"
    )
    required_gross_tp_bps_floor: float | None = Field(
        default=None, description="Minimum gross TP in bps"
    )
    min_rr: float | None = Field(
        default=None, description="Minimum risk/reward ratio")
    gross_tp_bps: float | None = Field(
        default=None, description="Actual gross target pnl in bps"
    )
    realized_pnl_net: float | None = Field(
        default=None, description="Realized net pnl (outcome)"
    )
    commission: float | None = Field(default=None)
    outcome: str | None = Field(
        default=None, description="Gate decision outcome"
    )
    counterfactual_source: str | None = Field(
        default=None, description="Source for counterfactual label if any"
    )
    exact_roundtrip: bool = Field(
        description="True if roundtrip complete"
    )
    source_paths: list[str] = Field(
        default_factory=list, description="Source files"
    )
    synthetic: bool = False

    model_config = {"extra": "forbid"}


class CalibrationWalkforwardManifestV1(BaseModel):
    """Manifest for walk-forward or time-series cross-validation split.

    Quality Level: DERIVED_LABELLED (metadata)
    Primary Purpose: Document train/validation/forward split boundaries.
    """

    dataset_schema: Literal["calibration_walkforward_manifest_v1"]
    dataset_version: str
    dataset_id: str = Field(
        description="Target dataset ID (e.g., 'calibration_market_bar_dataset_v1')")
    source_dataset: str = Field(description="Source/parent dataset if derived")
    train_start: str = Field(
        description="Start time of training split (ISO 8601 or date)")
    train_end: str = Field(description="End time of training split")
    validation_start: str = Field(description="Start time of validation split")
    validation_end: str = Field(description="End time of validation split")
    forward_start: str = Field(description="Start time of forward split")
    forward_end: str = Field(description="End time of forward split")
    excluded_sessions: list[str] = Field(
        default_factory=list,
        description="List of excluded session IDs/dates",
    )
    label_horizon_bars: int | None = Field(
        default=None, description="Label horizon in bars if applicable"
    )
    config_snapshot: dict[str, Any] = Field(
        description="Calibration config at time of split creation"
    )
    synthetic_allowed: bool = Field(
        description="Whether synthetic data is allowed in this manifest"
    )
    notes: str | None = Field(
        default=None, description="Free-form notes or caveats"
    )

    model_config = {"extra": "forbid"}
