"""
Pydantic V2 configuration models for AuroraTrader.

This module defines the complete configuration schema with full type validation.
All models are designed to fail fast (startup validation) rather than silently accepting invalid configs.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, model_serializer, ConfigDict


class InstrumentSpec(BaseModel):
    """Specification for a trading instrument (e.g., BTCUSDT)."""
    model_config = ConfigDict(
        extra='forbid')

    symbol: str = Field(...)
    step_size: str = Field(description='Quantity precision')
    tick_size: str = Field(description='Price precision')
    min_qty: str = Field()
    min_notional: str = Field(description='Minimum notional value in USDT')
    quote: str = Field()


class InstrumentPrecisionSpec(BaseModel):
    """Canonical Aurora instrument spec (SSOT from instruments.yaml).

    TASK50: Added min_qty and min_notional for fail-closed qty normalization.

    SIZING-MARGIN-FIRST-SSOT-02:
    - instruments.<SYM> is the SSOT for:
      - constraints: tick/step/min_qty/min_notional
      - execution: margin_mode + target_leverage (+policy)
      - sizing: margin_pct (margin-first, per-symbol)
    """

    model_config = ConfigDict(extra='forbid')

    symbol: str = Field(description="Symbol name (e.g., BTCUSDT)")
    tick_size: str = Field(description="Price precision")
    step_size: str = Field(
        description="Quantity precision (LOT_SIZE stepSize)")
    min_qty: str = Field(description="Minimum quantity (LOT_SIZE minQty)")
    min_notional: str = Field(
        description="Minimum notional value (MIN_NOTIONAL)")

    execution: "InstrumentExecutionConfig" = Field(
        description="Per-symbol execution SSOT (isolated/cross + target leverage policy)"
    )
    sizing: "InstrumentSizingConfig" = Field(
        description="Per-symbol sizing SSOT (margin-first: margin_pct)"
    )

    # Per-symbol flip orchestration (REQUIRED SSOT)
    flip: "FlipOrchestrationConfig" = Field(
        ...,  # REQUIRED - no default
        description="Per-symbol flip config (enabled + hysteresis_mult). REQUIRED for all active symbols."
    )


# ─────────────────────────────────────────────────────────────────────────────────
# Strategy-Level Leverage Configuration (P1: Active Leverage Management)
# ─────────────────────────────────────────────────────────────────────────────────
# Used in strategy per-asset configs (AuroraInstrumentConfig, MRAssetConfig)
# to specify target leverage per symbol.
#
# NOTE: This is SEPARATE from InstrumentExecutionConfig (instruments.yaml SSOT),
# which has additional fields like leverage_policy and max_notional_utilization.
# ─────────────────────────────────────────────────────────────────────────────────


class LeverageConfig(BaseModel):
    """Leverage configuration for strategy per-asset settings.

    P1: Active Leverage Management - explicit leverage in strategy configs.

    Used by:
    - AuroraInstrumentConfig.leverage (aurora.yaml → aurora.assets.<SYMBOL>.leverage)
    - MRAssetConfig.leverage (mean_reversion.yaml → mean_reversion.assets.<SYMBOL>.leverage)

    At startup, LeverageBootstrapper reads leverage from the strategy
    that owns the symbol (based on strategies.yaml assignments).
    """
    model_config = ConfigDict(extra='forbid')

    target: int = Field(
        ge=1, le=125,
        description='Target leverage (1-125). Binance Futures max is 125x.'
    )
    mode: Literal["ISOLATED", "CROSSED"] = Field(
        default="ISOLATED",
        description='Margin mode. ISOLATED recommended for position-level risk control.'
    )
    max_notional_value: Optional[Decimal] = Field(
        default=None,
        description='Optional: Max notional value cap for this leverage. From leverageBracket API.'
    )


class InstrumentExecutionConfig(BaseModel):
    """Per-instrument execution settings for leverage and margin control (TASK47c).

    All fields are MANDATORY for LIVE execution mode.
    Missing any field in LIVE mode → startup crash (fail-closed).

    GAP-LEV-01 + GAP-MAR-01: Leverage and margin mode must be part of execution contract.
    """
    model_config = ConfigDict(extra='forbid')

    margin_mode: Literal["isolated", "cross"] = Field(
        description='Binance margin mode. ISOLATED = per-position margin, CROSS = shared wallet margin.'
    )
    target_leverage: int = Field(
        ge=1, le=125,
        description='Target leverage for this instrument (1-125). Must match or be set on exchange.'
    )
    leverage_policy: Literal["verify_only", "set_and_verify"] = Field(
        description='verify_only = reject if mismatch. set_and_verify = set margin+leverage then verify.'
    )
    max_notional_utilization: float = Field(
        ge=0.0, le=1.0,
        description='Max notional as fraction of available capacity (0.0-1.0). Used for L1 capacity gate.'
    )


class InstrumentSizingConfig(BaseModel):
    """Per-instrument sizing SSOT (SIZING-MARGIN-FIRST-SSOT-02).

    Margin-first model:
    - margin_usdt = equity * margin_pct
    - notional_target = margin_usdt * leverage
    """

    model_config = ConfigDict(extra="forbid")

    margin_pct: float = Field(
        gt=0.0,
        le=1.0,
        description="Fraction of wallet equity allocated as isolated margin for this symbol (0..1].",
    )


class SignalWeights(BaseModel):
    """Weights for signal calculation (OBI, TFI, etc).

    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    R1: macro_resid added, macro_sync deprecated (Optional with default 0).
    """
    model_config = ConfigDict(extra='forbid')

    obi: float = Field()
    tfi: float = Field()
    delta_price: float = Field()
    ema_bias: float = Field()
    volume_spike: float = Field()
    volatility_state: float = Field()
    depth_imbalance: float = Field()
    # R1: macro_resid replaces macro_sync for directional scoring
    macro_resid: float = Field(
        description='R1: Beta-adjusted residual weight (SIGNED, neutral=0)')
    # DEPRECATED: macro_sync kept for backward compat, defaults to 0
    macro_sync: Optional[float] = Field(
        default=0.0,
        description='DEPRECATED: Use macro_resid. Kept for backward compat.'
    )


class BarGatingConfig(BaseModel):
    """Bar gating configuration for decision making."""
    model_config = ConfigDict(extra='forbid')
    enable: bool = Field()
    bar_ms: int = Field(description='Bar duration in milliseconds')


class BehaviorFsmConfig(BaseModel):
    """Behavioral FSM configuration."""
    model_config = ConfigDict(extra='forbid')
    enable: bool = Field()
    high_vol_multiplier: float = Field()
    low_vol_multiplier: float = Field()


class SignalsConfig(BaseModel):
    """Signals configuration (strategy-level, SSOT)."""
    model_config = ConfigDict(extra="forbid")

    normalize_signals_mode: Literal["off", "legacy_v1", "signed_v2"] = Field(
        description="Signal normalization mode. 'legacy_v1' is forbidden in live/production."
    )
    enable_new_metrics: bool = Field()
    delta_price_cap_pct: float = Field(
        gt=0.0,
        le=1.0,
        description="Delta price cap as pct of price (e.g. 0.02 = 2%). Required (no hardcoded fallback).",
    )


class DirectionStrengthScoringConfig(BaseModel):
    """Direction/Strength split configuration (strategy-level, SSOT)."""

    model_config = ConfigDict(extra="forbid")

    directional_features: List[str] = Field(
        description="Signed features that define direction (dir component)."
    )
    strength_features: List[str] = Field(
        description="Magnitude/confirmation features (strength component)."
    )
    strength_alpha: float = Field(
        ge=0.0,
        description="Strength influence: final = dir * (1 + strength_alpha * strength).",
    )
    strength_cap: float = Field(
        ge=0.0,
        description="Clamp for strength component (>=0).",
    )

    @model_validator(mode="after")
    def _validate_directional_nonempty(self) -> "DirectionStrengthScoringConfig":
        if not self.directional_features:
            raise ValueError(
                "directional_features must be non-empty (SSOT-required)")
        return self


class LiquidityGateConfig(BaseModel):
    """
    Configuration for Liquidity Gate (Score V2).

    Prevents trading if liquidity is too low (kappa < min) or readiness fails.
    This replaces the implicit 'liquidity_kappa' in signal weights.

    CONFIG HIERARCHY (resolution order, most specific wins):
    1. Per-asset config: strategies.<strategy>.assets.<SYMBOL>.liquidity_gate
    2. Global strategy config: strategies.<strategy>.liquidity_gate
    3. Decision config (Aurora only): strategies.aurora.decision.liquidity_gate

    Example resolution for BTCUSDT in MeanReversion:
    - If mean_reversion.assets.BTCUSDT.liquidity_gate is set → uses that
    - Else if mean_reversion.liquidity_gate is set → uses that
    - Else gate is disabled (passes all signals)
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(description="Enable liquidity gate")
    kappa_min: float = Field(
        ge=0.0, le=1.0, description="Minimum kappa required to pass gate")
    kappa_max: float = Field(default=1.0, ge=0.0, le=1.0,
                             description="Max kappa (clamping)")
    # TODO(NOT_IMPLEMENTED): failsafe_qty_check is parsed but NOT wired to runtime.
    # Intended: double-check min_qty requirements even after liquidity gate passes.
    # Status: Marked [DEAD] in docs/CONFIG_MAP.md. Remove field after confirming no YAML refs.
    failsafe_qty_check: bool = Field(
        default=True,
        description="[NOT_IMPLEMENTED] Reserved: double-check min_qty even if gate passes"
    )


class PositionSizingConfig(BaseModel):
    """Position sizing configuration.

    TASK-ZOMBIE-FIX: Removed dead fields (kappa_mode, liquidity_kappa,
    risk_fraction_q, liquidity_kappa_mode) - never wired to runtime.
    """
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    min_position_size_usd: float = Field()
    liquidity_based_cap_usd: float = Field()


class KellyConfig(BaseModel):
    """Kelly criterion configuration."""
    model_config = ConfigDict(extra='forbid')
    base_probability: float = Field()
    kelly_cap: float = Field()
    kelly_alpha: float = Field()
    payoff_ratio_r: float = Field()
    # Phase 4: Remove hardcoded bounds
    p_min: float = Field(default=0.45, description="Minimum probability clamp")
    p_max: float = Field(default=0.65, description="Maximum probability clamp")
    uplift_factor: float = Field(
        default=0.20, description="Score-to-probability uplift multiplier")


class QosConfig(BaseModel):
    """Quality of Service configuration for rate limiting."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    exposure_block_cooldown_sec: int = Field()
    # Global fallback for per-symbol cooldown (strategies.aurora.assets.<SYMBOL>.cooldown_sec takes priority)
    symbol_cooldown_sec: int = Field(
        description='Global fallback cooldown. Per-symbol config takes priority.')
    max_intents_per_minute_per_symbol: int = Field()
    mode: str = Field(description='defer | block')
    enforce: bool = Field()
    apply_to_strategies: List[str] = Field(
        default_factory=list,
        description=(
            "Optional allowlist of strategy_id values that should have QoS applied in the strategy gateway. "
            "Empty => apply to all strategies (backward compatible)."
        ),
    )


class ROIExitConfig(BaseModel):
    """ROI Exit Strategy configuration."""
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field()
    target_roi_pct: float = Field()


# TASK-ZOMBIE-FIX: Removed FailsafeConfig class (dead, max_hold_sec moved to AuroraExitConfig)


class MeanReversionConfig(BaseModel):
    """Configuration for Mean Reversion regime model (regime.yaml SSOT).

    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema, no runtime surprises).
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field()
    bb_window: int = Field()
    bb_std_dev: float = Field()
    min_vol_atr: float = Field()
    allowed_regimes: List[str] = Field()


# ============================================================================
# Mean Reversion 1m Strategy Configuration (Track B)
# ============================================================================

class MRStrategyParamsConfig(BaseModel):
    """Strategy parameters for Mean Reversion 1m.

    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')

    bb_window: int = Field(description='Bollinger Bands window')
    bb_num_std: float = Field(description='BB standard deviations')
    atr_window: int = Field(description='ATR window for stops')
    rsi_window: int = Field(description='RSI window')

    entry_threshold: float = Field(description='%B threshold for entry')
    rsi_oversold: float = Field(description='RSI oversold level')
    rsi_overbought: float = Field(description='RSI overbought level')

    min_bars: int = Field(description='Min bars before trading')
    min_bb_width: float = Field(description='Min BB width')
    max_bb_width: float = Field(description='Max BB width')

    sl_atr_mult: float = Field(description='SL as ATR multiplier')
    tp_to_mid: bool = Field(description='Target mid BB')
    cooldown_sec: int = Field(description='Cooldown between signals')


class MRRegimeThresholdsConfig(BaseModel):
    """Regime thresholds for FLAT regime classification.

    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')

    high_vol_pct: float = Field(description='ATR% for FLAT_HIGH')
    low_vol_pct: float = Field(description='ATR% for FLAT_LOW')


class MRStrategyOverrideConfig(BaseModel):
    """Per-asset strategy parameter overrides for MR.

    These override the global MRStrategyParamsConfig values for a specific symbol.
    """
    model_config = ConfigDict(extra='forbid')

    bb_window: Optional[int] = Field(
        default=None, description='BB window size')
    bb_num_std: Optional[float] = Field(
        default=None, description='BB std multiplier')
    min_bb_width: Optional[float] = Field(
        default=None, description='Min BB width filter')
    entry_threshold: Optional[float] = Field(
        default=None, description='Entry distance threshold')
    tp_to_mid: Optional[bool] = Field(
        default=None, description='TP to mid vs outer band')
    sl_atr_mult: Optional[float] = Field(
        default=None, description='SL ATR multiplier override')
    cooldown_sec: Optional[int] = Field(
        default=None, description='Cooldown between trades')
    sl_buffer_pct: Optional[float] = Field(
        default=None, description='Additional SL buffer percentage (0.002 = 0.20%)')
    tp_buffer_pct: Optional[float] = Field(
        default=None, description='Additional TP buffer percentage (0.002 = 0.20%)')
    allowed_regimes: Optional[List[str]] = Field(
        default=None, description='Override allowed regimes for this symbol')


class MRAssetConfig(BaseModel):
    """Per-asset configuration for Mean Reversion 1m.

    UPDATED: Now supports typed strategy/risk overrides.
    P1: Added leverage field for Active Leverage Management.
    """
    model_config = ConfigDict(
        extra='forbid')  # CFG-LEGACY-SUNSET-11: YAML migration complete

    enabled: bool = Field()

    # P1: Active Leverage Management - per-asset leverage config
    leverage: Optional["LeverageConfig"] = Field(
        default=None,
        description='Per-asset leverage configuration. Read by LeverageBootstrapper at startup.'
    )

    # NEW: Typed strategy overrides
    strategy: Optional[MRStrategyOverrideConfig] = Field(
        default=None, description='Strategy parameter overrides for this symbol')

    # Phase 4: Liquidity Gate override
    liquidity_gate: Optional[LiquidityGateConfig] = Field(
        default=None, description="Per-asset liquidity gate override")

    allowed_regimes: List[str] = Field(
        description='Regimes where trading is allowed')

    position_mode: Literal["STRICT", "DYNAMIC"] = Field(
        description='STRICT = No pyramiding (1 trade only), DYNAMIC = Pyramiding allowed up to cap')


class MRRegimeSizingConfig(BaseModel):
    """Sizing/stop/target multipliers for a specific FLAT regime.

    CFG-LEGACY-SUNSET-11: Converted to extra='forbid' (known schema).
    """
    model_config = ConfigDict(extra='forbid')

    sizing_mult: float = Field()
    stop_mult: float = Field()
    target_mult: float = Field()


# DM-SAFETY-BYPASSES-P1: Safety gates configuration
class SafetyGatesConfig(BaseModel):
    """Safety gates control for directional sanity and price motion gates.

    DM-SAFETY-BYPASSES-P1: Replaces hardcoded strategy_id == 'aurora' check.
    - Aurora (trend-following): enabled=true → gates APPLY
    - Mean Reversion (counter-trend): enabled=false → gates SKIPPED
    - Missing config → FAIL-CLOSED (trade blocked)
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        description='Enable directional sanity and price motion gates for this strategy'
    )


class MeanReversion1mStrategyConfig(BaseModel):

    """
    Full configuration for Mean Reversion 1m Strategy.

    Config is provided via config.strategies.mean_reversion (loaded from strategy profile SSOT).
    """
    model_config = ConfigDict(extra='forbid')

    # Master enable flag (feature flag)
    enabled: bool = Field(description='Enable MR 1m strategy')

    # Timeframe
    timeframe_sec: int = Field(
        ge=60, le=3600, description='Bar timeframe in seconds')

    # Strategy parameters
    strategy: MRStrategyParamsConfig = Field()

    # Regime thresholds
    regime_thresholds: MRRegimeThresholdsConfig = Field()

    # Per-asset configurations (symbol → config)
    assets: Dict[str, MRAssetConfig] = Field()

    # Regime sizing (regime_name → multipliers)
    regime_sizing: Dict[str, MRRegimeSizingConfig] = Field()

    # Global allowed regimes whitelist (can be overridden per-asset in assets.X.allowed_regimes)
    allowed_regimes: List[str] = Field(
        description='Whitelist of Flat regimes to trade in (global default)')

    # Phase 4: Liquidity Gate (Global)
    liquidity_gate: Optional[LiquidityGateConfig] = Field(
        default=None, description="Global liquidity gate for MR")

    # ORDER-POLICY-01: Execution policy
    execution: "StrategyExecutionConfig" = Field(
        description="Execution policy (SSOT)")

    # DM-SAFETY-BYPASSES-P1: Safety gates configuration
    safety_gates: SafetyGatesConfig = Field(
        description="Safety gates control (directional/price motion gates)"
    )


# ==============================================================================
# STRATEGIES REGISTRY (CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION)
# ==============================================================================

class StrategiesArbitrationLoggingConfig(BaseModel):
    """Logging configuration for strategy arbitration."""
    model_config = ConfigDict(extra='forbid')

    rejected_why_prefix: str = Field(
        description='Prefix for why-codes when strategy intent is rejected')
    log_level: str = Field(
        description='Log level for arbitration events (INFO/WARNING/ERROR)')


class StrategiesArbitrationConfig(BaseModel):
    """Configuration for strategy conflict arbitration."""
    model_config = ConfigDict(extra='forbid')

    mode: Literal['priority'] = Field(
        description="Arbitration mode: 'priority' (only supported mode, lower number = higher priority)")
    window_ms: int = Field(
        description="Decision window size in ms for multi-strategy arbitration (SSOT; no silent defaults).")
    priority: Dict[str, int] = Field(
        description='Strategy priority ranks (lower = higher priority)')
    logging: StrategiesArbitrationLoggingConfig = Field()


class StrategiesRegistryConfig(BaseModel):
    """
    Strategies Registry SSOT (config/aurora/strategies.yaml).

    Defines:
    1. Which strategies are active per symbol (assignments)
    2. How to arbitrate conflicts between strategies (arbitration)

    CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Strict validation (extra='forbid')
    """
    model_config = ConfigDict(extra='forbid')

    version: str = Field(description='Strategies registry config version')
    assignments: Dict[str, List[str]] = Field(
        description='Per-symbol strategy assignments (symbol → list[strategy_id])')
    arbitration: StrategiesArbitrationConfig = Field(
        description='Arbitration policy for strategy conflicts')

    @model_validator(mode='after')
    def validate_priorities_for_hybrid_symbols(self) -> 'StrategiesRegistryConfig':
        """Ensure all strategies in hybrid assignments have priorities defined."""
        if self.arbitration.mode == 'priority':
            priorities = self.arbitration.priority
            for symbol, strategies in self.assignments.items():
                if len(strategies) > 1:  # Hybrid symbol
                    for strategy_id in strategies:
                        if strategy_id not in priorities:
                            raise ValueError(
                                f"❌ ARBITRATION:missing_priority for '{strategy_id}' in hybrid "
                                f"symbol {symbol}. All strategies must have priorities defined."
                            )
        return self


class DecisionModeOverrideConfig(BaseModel):
    """Mode-specific decision overrides (testnet/production).

    CFG-DICT-ANY-BURN-13: Typed config for mode overrides.
    Allows ANY field from DecisionConfig to be overridden.
    extra='allow' justified: config_loader merges ANY override key.
    """
    model_config = ConfigDict(extra='forbid')  # Justified: dynamic merge

    # Common overrides (known patterns from config_loader.py L120-140)
    signal_threshold: Optional[float] = Field()
    # Other DecisionConfig fields can be overridden dynamically


class AnchorShockVetoConfig(BaseModel):
    """Anchor Shock Veto configuration.

    Phase 3 Fix: Block BUY signals when anchor (BTC) is crashing.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=False, description="Enable anchor shock veto")
    anchor_symbol: str = Field(
        default="BTCUSDT", description="Symbol used as anchor")
    threshold: float = Field(
        default=-2.0, description="Block BUY if macro_resid < threshold")


class HoldingPeriodConfig(BaseModel):
    """Minimum Holding Period configuration (Anti-Churn Gate).

    RFC: docs/RFC_min_duration_logic.md
    Prevents HFT-style churn by enforcing minimum time in position before
    allowing signal-based exits. Does NOT affect safety exits (SL/TP/Risk).
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=False, description="Enable minimum holding period gate")
    min_duration_sec: float = Field(
        default=30.0, description="Minimum seconds to hold position before allowing signal-based exit")
    emergency_exit_threshold: float = Field(
        default=0.7, description="|score| threshold for emergency override (allows exit even within holding period)")
    apply_to_flips: bool = Field(
        default=True, description="Also apply holding period to FLIP signals (not just exits)")


class VolAdjGatesConfig(BaseModel):
    """Volume-Adjusted Gates configuration (VOL-ADJ-GATES-01).

    Anti-Flat: Block entry when normalized motion < threshold (fee churn in dead market).
    Anti-FOMO: Block entry when normalized motion > threshold (snapback risk).

    Uses pm_norm_<window>s from price_motion feature domain.
    Formula: pm_norm = clip(ret_window / (k_vol * vol_window), -1, 1)
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=False, description="Enable vol-adj gates (Anti-Flat + Anti-FOMO)")
    anti_flat_sigma: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Block ENTRY if |pm_norm| < anti_flat_sigma (dead market, fee churn)"
    )
    anti_fomo_sigma: float = Field(
        default=4.0,
        ge=1.0,
        le=10.0,
        description="Block ENTRY if |pm_norm| > anti_fomo_sigma (extreme impulse, snapback risk)"
    )
    motion_window_sec: int = Field(
        default=900,
        ge=10,
        description="Which pm_norm window to use: 10, 60, 300, or 900 (seconds)"
    )


class DecisionConfig(BaseModel):
    """Decision making configuration (testnet/production overrides).

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields explicit).
    """
    model_config = ConfigDict(extra='forbid')

    # Mode-specific configs (typed, not Dict[str, Any])
    testnet: Optional[DecisionModeOverrideConfig] = Field()
    production: Optional[DecisionModeOverrideConfig] = Field()

    # IMPORTANT: Default exists for test compatibility, but production MUST override
    signal_threshold: float = Field(
        description='Signal score threshold. PRODUCTION MUST OVERRIDE in trading.yaml!')
    cooldown_sec: Optional[int] = Field(
        description='Global cooldown (deprecated, use per-instrument)')
    side_bias_min_score: Optional[float] = Field(
        description='Min score for side bias')
    side_bias_penalty_factor: Optional[float] = Field(
        description='Side bias penalty factor')
    side_bias_target_ratio: Optional[float] = Field(
        description='Side bias target ratio')
    side_bias_window_sec: Optional[int] = Field(
        description='Side bias window (seconds)')
    side_bias_min_intents: Optional[int] = Field(
        description="Minimum number of intents required in window to activate side-bias penalty"
    )
    side_bias_min_intents: int = Field(
        default=18, description='Min intents in window to activate side bias penalty')

    # Retry configuration (formerly legacy defaults)
    retry_ttl_ms: int = Field(description='Retry TTL in ms')
    retry_max_count: int = Field(description='Max retry attempts')
    retry_backoff_factor: float = Field(description='Retry backoff multiplier')

    signal_weights: SignalWeights = Field()
    signals: SignalsConfig = Field()
    direction_strength_scoring: DirectionStrengthScoringConfig = Field(
        description="Direction/Strength split scoring configuration (SSOT-required)."
    )
    kelly: KellyConfig = Field()
    qos: QosConfig = Field()

    bar_gating: Optional[BarGatingConfig] = Field()
    behavior_fsm: Optional[BehaviorFsmConfig] = Field()
    roi_exit: Optional[ROIExitConfig] = Field()
    mean_reversion: Optional[MeanReversionConfig] = Field()

    regime_thresholds: Dict[str, float] = Field(
        description='Regime-specific signal thresholds')
    regime_threshold_multipliers: Dict[str, float] = Field(
        description='Regime threshold multipliers')
    blocked_regimes: Optional[List[str]] = Field(
        default=None,
        description=(
            "Regime kill-switch: if current regime is in this list, suppress Aurora strategy signals "
            "(no entry/exit/hold/flip intents from strategy; safety exits like SL/TP still apply)."
        ),
    )
    symbols_to_track: Optional[List[str]] = Field(
        default=None, description='DEPRECATED: Use instruments SSOT')
    neutral_threshold: Optional[float] = Field(
        description='Neutral zone threshold')

    # Phase 4: Score V2 Global Configuration
    scoring_version: Literal["v1", "v2"] = Field(
        default="v1", description="Scoring engine version")
    feature_neutrals: Dict[str, float] = Field(
        default_factory=dict, description="Neutral offsets for V2 scoring")
    essential_features: List[str] = Field(
        default_factory=list, description="Features that must be present/ready")
    liquidity_gate: Optional[LiquidityGateConfig] = Field(
        default=None, description="Global liquidity gate config")
    anchor_shock_veto: Optional[AnchorShockVetoConfig] = Field(
        default=None, description="Phase 3: Block BUY during anchor crash")

    # Anti-Churn Gate: Minimum Holding Period
    holding_period: Optional[HoldingPeriodConfig] = Field(
        default=None, description="RFC: docs/RFC_min_duration_logic.md - Prevents HFT churn")

    # Re-entry Cooldown (Anti-Ping-Pong Gate)
    reentry_cooldown_sec: Optional[int] = Field(
        default=60, description="Global cooldown after position closes before allowing new entry")

    # VOL-ADJ-GATES-01: Sigma-normalized motion gates (Anti-Flat + Anti-FOMO)
    gates: Optional[VolAdjGatesConfig] = Field(
        default=None, description="VOL-ADJ-GATES-01: Block entries in dead/extreme markets")

    # EP-01.2-INT: EntryPlan
    entry_plan: Optional["EntryPlanConfig"] = Field(
        default=None, description="EP-01.2-INT: EntryPlan configuration")

    @model_validator(mode="after")
    def _validate_direction_strength_contract(self) -> "DecisionConfig":
        ds = getattr(self, "direction_strength_scoring", None)
        if ds is None:
            raise ValueError("direction_strength_scoring is required (SSOT)")

        essentials = set(getattr(self, "essential_features", []) or [])
        directional = set(getattr(ds, "directional_features", []) or [])
        missing = sorted(essentials - directional)
        if missing:
            raise ValueError(
                "direction_strength_scoring.directional_features must include all essential_features; "
                f"missing: {missing}"
            )
        return self


class SLConfig(BaseModel):
    """Stop-loss configuration."""
    model_config = ConfigDict(extra='forbid')
    fixed_bps: int = Field(description='Fixed basis points')


class TPConfig(BaseModel):
    """Take-profit configuration."""
    model_config = ConfigDict(extra='forbid')
    fixed_bps: int = Field(description='Fixed basis points')


class BracketsConfig(BaseModel):
    """Brackets (TP/SL) configuration."""
    model_config = ConfigDict(extra='forbid')

    sl: Optional[SLConfig] = Field()
    tp: Optional[TPConfig] = Field()
    oco_emulation: bool = Field(description='Emulate OCO orders')
    # TASK-ZOMBIE-FIX: Removed stop_loss_bps (dead duplicate, SSOT is sl.fixed_bps)
    offset_bps: int = Field(description='Safety offset in bps')


class TrailingDefaultsConfig(BaseModel):
    """Global trailing stop defaults (used when per-instrument not specified)."""
    model_config = ConfigDict(extra='forbid')

    activation_pct: float = Field(
        default=0.003, description='0.3% profit to activate')
    trail_pct: float = Field(
        default=0.006, description='0.6% trailing distance')
    min_update_interval_sec: int = Field(
        default=5, description='Min seconds between updates')


class EmergencyConfig(BaseModel):
    """Emergency stop-loss configuration (margin-based).

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Added wait_mode_bars (fsm_manage.py:120).
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(description='Enable emergency SL')
    wait_mode_bars: int = Field(
        default=2, description='Wait mode bars before resuming')
    emergency_sl_bps: int = Field(
        default=100, description='Emergency SL in basis points')


class OrphanMonitorConfig(BaseModel):
    """Orphan bracket monitor configuration.

    CFG-DICT-ANY-BURN-13: Typed config (consumption in fsm.py L166).
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(description='Enable orphan monitoring')
    run_on_startup: bool = Field(
        description='Run orphan check immediately on FSM startup')
    periodic_interval_sec: int = Field(
        ge=5, description='Interval between orphan checks')
    min_order_age_sec: int = Field(
        ge=0, description='Minimum age of order before considering it for orphan cleanup')
    batch_cancel_limit: int = Field(
        ge=1, description='Max number of orders to cancel in one batch')
    rate_limit_per_min: int = Field(
        ge=1, description='Rate limit for cancel requests per minute')


class ManageConfig(BaseModel):
    """Order management configuration.

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields typed).
    """
    model_config = ConfigDict(extra='forbid')

    brackets: Optional[BracketsConfig] = Field()
    emergency: Optional[EmergencyConfig] = Field()
    auto: bool = Field()
    orphan_monitor: Optional[OrphanMonitorConfig] = Field()
    # TASK-ZOMBIE-FIX: Removed failsafe field (dead, max_hold_sec moved to instruments.<SYM>.exit)


class ExposureConfig(BaseModel):
    """Exposure guard configuration.

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields known).
    """
    model_config = ConfigDict(extra='forbid')

    max_equity_utilization_pct: float = Field()
    max_portfolio_fraction: float = Field()
    # TASK-ZOMBIE-FIX: Removed max_side_utilization_pct (dead, never read in exposure_guard)
    max_directional_ratio: float = Field()
    # TASK-ZOMBIE-FIX: Removed per_symbol_cap_pct (dead, never read in exposure_guard)
    pending_ttl_sec: int = Field()
    # TASK-ZOMBIE-FIX: Removed pending_reservation_ttl_sec (dead, never read in exposure_guard)
    post_fill_hold_ttl_sec: int = Field()
    # TASK-ZOMBIE-FIX: Removed positions_stale_ttl_sec (duplicate, SSOT is domains.execution_position.exposure_guard.stale_ttl_sec)
    leverage_defaults: Dict[str, int] = Field()
    count_pending_orders: bool = Field(
        description='Count pending orders in exposure')
    exclude_reduce_only: bool = Field(
        description='Exclude reduce-only from exposure')


class WatchdogConfig(BaseModel):
    """Watchdog configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    ack_ttl_ms: int = Field()
    fill_ttl_ms: int = Field()
    check_interval_ms: int = Field()
    rps_limit: int = Field()


class SMARegimeModelConfig(BaseModel):
    """Configuration for SMA-based trend regime detection.

    Detects TREND_UP, TREND_DOWN, MEAN_REVERSION based on SMA crossover.
    """
    model_config = ConfigDict(extra='forbid')

    sma_short_period: int = Field(
        ge=2, description='Short SMA period for trend detection')
    sma_long_period: int = Field(
        ge=5, description='Long SMA period for trend detection')
    confidence_multiplier: float = Field(
        ge=1.0, description='Confidence scaling factor')
    confidence_min: float = Field(
        ge=0.0, le=1.0, description='Minimum confidence value')
    confidence_max: float = Field(
        ge=0.0, le=1.0, description='Maximum confidence value')


class VolatilityRegimeModelConfig(BaseModel):
    """Configuration for ATR-based volatility regime detection.

    Detects HIGH_VOLATILITY, LOW_VOLATILITY based on ATR vs historical average.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(description='Enable volatility regime detection')
    atr_period: int = Field(ge=1, description='ATR calculation period')
    atr_sma_length: int = Field(
        ge=10, description='ATR SMA length for baseline')
    allow_close_to_close_atr: bool = Field(
        description='Allow close-to-close TR/ATR when OHLC is unavailable (explicit opt-in)')
    threshold_multiplier: float = Field(
        ge=1.0, description='High vol threshold (ATR > threshold_mult * avg)')
    low_vol_multiplier: float = Field(
        ge=0.0, le=1.0, description='Low vol threshold (ATR < low_vol_mult * avg)')
    high_vol_confidence_multiplier: float = Field(
        ge=1.0, description='Confidence scaling for high vol')
    low_vol_confidence_multiplier: float = Field(
        ge=1.0, description='Confidence scaling for low vol')


class MeanReversionRegimeModelConfig(BaseModel):
    """Configuration for mean reversion regime detection.

    Detects MEAN_REVERSION when price is close to both SMAs.
    """
    model_config = ConfigDict(extra='forbid')

    threshold: float = Field(
        ge=0.0, description='Max price deviation from SMAs for MR regime')
    confidence_multiplier: float = Field(
        ge=1.0, description='Confidence scaling factor')


class RegimeModelsConfig(BaseModel):
    """Container for all regime detection model configurations.

    Loaded from regime.yaml 'models' section.

    CFG-FEATURES-REGIME-SSOT-04: extra='forbid' for strict validation
    """
    model_config = ConfigDict(extra='forbid')

    sma_trend: SMARegimeModelConfig = Field(description='SMA trend model')
    volatility: VolatilityRegimeModelConfig = Field(
        description='Volatility model')
    mean_reversion: MeanReversionRegimeModelConfig = Field(
        description='Mean reversion model')


class RegimeModelConfig(BaseModel):
    """Base configuration for regime detection models."""
    model_config = ConfigDict(extra='forbid')

    confidence_multiplier: float = Field()
    confidence_min: float = Field()
    confidence_max: float = Field()


class RegimeDetectorConfig(BaseModel):
    """Regime detector configuration."""
    model_config = ConfigDict(extra='forbid')

    models: RegimeModelsConfig = Field(
        description='Regime detection models config')


class FallbackConfig(BaseModel):
    """Fallback configuration for execution.

    P1-CONFIG-EXTRACTION: Typed fields for fail-closed fallback mode.
    Consumed by: exposure_guard.py:_load_fallback_config()
    """
    model_config = ConfigDict(extra='forbid')

    policy: Literal["fail_closed", "reduce_exposure"] = Field(
        description="Fallback policy: fail_closed = block all new orders, reduce_exposure = scale down"
    )
    risk_reduction_pct: Decimal = Field(
        description="Exposure reduction percentage when policy=reduce_exposure (0.0-1.0)"
    )
    backoff_ms: List[int] = Field(
        description="Backoff intervals for retry attempts (ms)"
    )


class LimitOrdersConfig(BaseModel):
    """Limit orders configuration.

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Typed (limit_order_monitor.py:93).
    """
    model_config = ConfigDict(extra='forbid')

    # Add fields when consumption patterns documented


class OrdersConfig(BaseModel):
    """Orders configuration (TTL, retries, etc.).

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Typed (fsm.py:282 default_ttl_seconds).
    """
    model_config = ConfigDict(
        extra='forbid')  # Temporary: market/cancel sub-configs unknown

    default_ttl_seconds: int = Field(description='Default order TTL')


class ExecutionConfig(BaseModel):
    """Execution configuration.

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields explicit).
    """
    model_config = ConfigDict(extra='forbid')

    manage: Optional[ManageConfig] = Field()
    exposure: Optional[ExposureConfig] = Field()
    # Typed (ack_ttl_ms, fill_ttl_ms, rps_limit)
    watchdog: Optional[WatchdogConfig] = Field()

    # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Newly typed configs
    fallback: Optional[FallbackConfig] = Field()
    limit_orders: Optional[LimitOrdersConfig] = Field()
    orders: Optional[OrdersConfig] = Field()

    # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Explicit runtime fields (consumption proven)
    fsm_periodic_cleanup_enabled: bool = Field(
        description='FSM periodic cleanup')
    cooldown_after_close_ms: int = Field(
        ...,
        description="Global cooldown after any position closes (ms). Blocks new CMD:OPEN during this window.",
    )
    anti_race_close_ms: int = Field(description='Anti-race window (ms)')

    # PURGE-DIRTY-DOZEN: Removed dead fields (open_order_type, min_post_interval_per_symbol_ms) - 2026-01-25
    # Remaining DEPRECATED fields kept for backward compat parsing only:
    order_params: Optional[Dict[str, Any]] = Field(
        default=None, description='DEPRECATED: No consumption found')
    preflight_backoff_ms: Optional[List[int]] = Field(
        default=None, description='DEPRECATED: No consumption found')
    allow_trade_with_guardian_tidy_only: Optional[bool] = Field(
        default=None, description='DEPRECATED')
    order_guardian: Optional[Dict[str, Any]] = Field(
        default=None, description='DEPRECATED: Guardian not config')


class MacroSyncConfig(BaseModel):
    """Macro sync configuration for market data."""
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field(
        description='Enable macro sync (anchor subscription and events)')
    anchors: List[str] = Field(
        description='Anchor symbols for macro alignment')
    window: int = Field(description='Window in seconds')
    emit_abs: bool = Field(
        description='DEPRECATED: Not implemented. Planned removal: v2.0')

    # D4 Phase 1: Alignment mode for correlation calculation
    align_mode: str = Field(
        description="Alignment mode: 'strict_len' (exact match) or 'tail_min_len' (use min overlap tail)")
    min_buffer_size: int = Field(
        description='Min samples in buffer for correlation')
    time_diff_threshold_ms: int = Field(
        description='Max time diff (ms) between ticks for return calculation')
    anchor_update_from_ticks: bool = Field(
        description='Update anchor buffers from symbol ticks (false = EVT:ANCHOR_UPDATED only)')


# PURGE-DIRTY-DOZEN: Removed KlinesConfig, ApiCallLimits classes (dead stubs, REST replaced by WebSocket) - 2026-01-25


class BarAggregatorConfig(BaseModel):
    """Bar aggregator SSOT configuration.

    BAR-SSOT-002: Configuration for BarAggregator wiring.
    If enabled=True, timeframes_sec is mandatory.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        description='Enable bar aggregator (EVT:BAR_CLOSED emission)')
    timeframes_sec: List[int] = Field(
        description='Bar timeframes in seconds (e.g., [180, 300] for 3m and 5m)')


class MarketDataConfig(BaseModel):
    """Market data configuration.

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields known).
    """
    model_config = ConfigDict(extra='forbid')

    poll_interval_sec: float = Field()
    use_multiprocessing: bool = Field(description='Enable multiprocessing')
    websocket_streams: List[str] = Field()
    # PURGE-DIRTY-DOZEN: Removed api_call_limits (dead stub, REST replaced by WebSocket) - 2026-01-25
    macro_sync: Optional[MacroSyncConfig] = Field()
    bar_aggregator: Optional[BarAggregatorConfig] = Field(
        default=None, description='Bar aggregator config (optional, disabled if missing)')


class FeatureEngineeringConfig(BaseModel):
    """Feature engineering configuration."""
    model_config = ConfigDict(extra='forbid')

    ema: Dict[str, Any] = Field()
    volume: Dict[str, Any] = Field()
    volatility: Dict[str, Any] = Field()
    liquidity: Dict[str, Any] = Field()
    macro_sync: Dict[str, Any] = Field()


# ============================================================================
# Domain-Specific Configuration Models
# ============================================================================

# Note: PositionSizingConfig, QosConfig, SignalsConfig are defined above
# and reused here to avoid duplication.


class RiskSkewConfig(BaseModel):
    """Risk skew guard configuration (Commit 5)."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    max_skew_sec: int = Field(
        description='Max age difference between features.ts and risk.ts')
    max_defer_count: int = Field(
        description='Max DEFERs per symbol before NO_TRADE_UNTIL_REFRESH')
    defer_cooldown_sec: int = Field(
        description='Cooldown between deferred retries')
    defer_window_sec: int = Field(
        description='Window duration (seconds) - resets defer_count after this period')
    until_refresh_retry_sec: int = Field(
        description='Retry delay when in NO_TRADE_UNTIL_REFRESH state')


class RiskGateConfig(BaseModel):
    """Risk gate alert thresholds for blocked intents monitoring."""
    model_config = ConfigDict(extra='forbid')

    threshold_pct_testnet: float = Field(
        description='Alert if >X% intents blocked (testnet)')
    threshold_pct_production: float = Field(
        description='Alert if >X% intents blocked (production)')
    min_intents_for_check: int = Field(
        description='Minimum intents before checking threshold')


class FeaturesTtlConfig(BaseModel):
    """Features TTL configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    ttl_sec: int = Field()


# Note: BarGatingConfig and BehaviorFsmConfig already exist above


class ArmingConfig(BaseModel):
    """Arming/Warmup configuration for DecisionMaking."""
    model_config = ConfigDict(extra='forbid')

    require_regime_warmup: bool = Field()
    retry_backoff_ms: int = Field()
    max_attempts: int = Field()


class DirectionalSanityConfig(BaseModel):
    """Directional sanity gate configuration (DM-DIR-FORENSIC-01).

    Fail-closed semantics live in runtime code: when enabled and trend is
    not confidently confirmed, DM denies opening trades.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        description='Enable directional sanity gate (fail-closed)')
    min_abs_delta_price: float = Field(
        ge=0.0,
        description='Minimum absolute delta_price to consider trend (noise threshold)'
    )
    min_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description='Minimum confidence required (max(regime_confidence, trend_confidence))'
    )
    consecutive_bars: int = Field(
        ge=1,  # FIX-NRR026-BACKTEST: Allow 1 for bar-based backtest (was ge=2)
        le=3,
        description='Number of consecutive deltas required to confirm trend (1–3). Use 1 for bar-based backtest, 2+ for live tick-based.'
    )


class PriceMotionSanityConfig(BaseModel):
    """Multi-window price-motion sanity gate configuration (SSOT-required).

    Used to block opening positions against persistent price motion, even if
    microstructure signals (e.g., OBI) are favorable.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        description="Enable price-motion sanity gate (fail-closed)")
    k_vol: float = Field(
        gt=0.0, description="Normalization factor: pm_norm = ret/(k_vol*vol_pct)")
    flash_window_sec: int = Field(
        ge=1, le=300, description="Flash window length (seconds)")
    bleed_window_sec: int = Field(
        ge=10, le=3600, description="Bleed window length (seconds)")
    flash_threshold_norm: float = Field(
        ge=0.0, description="DENY if pm_norm_flash <= -threshold for LONG")
    bleed_threshold_norm: float = Field(
        ge=0.0, description="DENY if pm_norm_bleed <= -threshold for LONG")
    require_bleed_ready: bool = Field(
        description="If true: missing bleed window data => DENY (fail-closed)")
    # VOL-ADJ-GATES-CLIP-CONFIG-01: pm_norm clipping bound for Anti-FOMO detection
    pm_norm_clip_abs: float = Field(
        default=10.0,
        gt=0.0,
        le=50.0,
        description="Absolute clipping bound for pm_norm: clip to [-clip_abs, +clip_abs]. Default 10.0 for Anti-FOMO."
    )


class FlipOrchestrationConfig(BaseModel):
    """Per-symbol flip-orchestration tuning (close-on-reversal).

    STRICT SSOT: No defaults. Every active symbol MUST have explicit flip config.

    This is a *smoothing* layer for tick-based signals:
    it prevents immediate flip-closes on marginal opposite signals.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ...,  # REQUIRED - no default
        description="Enable flip hysteresis for this symbol.",
    )
    hysteresis_mult: float = Field(
        ...,  # REQUIRED - no default
        ge=1.0,
        description=(
            "Require stronger opposite signal before emitting reduce-only CLOSE during flip. "
            "Example: 1.3 means opposite score must exceed its threshold by 30%."
        ),
    )


class GlobalFlipKillswitchConfig(BaseModel):
    """Global FLIP killswitch for DecisionMaking.

    STRICT SSOT: No defaults. Must be explicitly set in domains.yaml.

    If disabled, ALL flip logic is OFF regardless of per-symbol settings.
    Per-symbol tuning (enabled + hysteresis_mult) is in instruments.yaml.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ...,  # REQUIRED - no default
        description="Master killswitch for FLIP. If false, all flip disabled globally.",
    )


class EntryPlanConfig(BaseModel):
    """
    EntryPlan configuration for ATR-based entry/SL/TP computation.

    EP-01.2-INT: Strict validation (extra='forbid'), no silent defaults.
    All parameters must be explicitly set in domains.yaml.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        description="Enable EntryPlan-based SL/TP injection into trade intents"
    )
    atr_period: int = Field(
        ge=1, le=100,
        description="Expected ATR period (for validation/tracing, must match FE config)"
    )
    entry_k_atr: float = Field(
        gt=0.0, le=5.0,
        description="Entry offset as ATR multiplier (e.g., 0.5 = 0.5*ATR from ref price)"
    )
    sl_k_atr: float = Field(
        gt=0.0, le=10.0,
        description="Stop-loss distance as ATR multiplier (e.g., 1.5 = 1.5*ATR)"
    )
    tp_k_atr: float = Field(
        gt=0.0, le=10.0,
        description="Take-profit distance as ATR multiplier (e.g., 2.0 = 2.0*ATR)"
    )
    obi_weight: float = Field(
        ge=0.0, le=2.0,
        description="OBI modulation weight (0 = no modulation, 1 = full modulation)"
    )
    obi_mod_clamp_min: float = Field(
        gt=0.0, le=1.0,
        description="Minimum clamp for OBI multiplier (anti-taker drift safety)"
    )
    obi_mod_clamp_max: float = Field(
        ge=1.0, le=3.0,
        description="Maximum clamp for OBI multiplier (anti-taker drift safety)"
    )
    require_atr: bool = Field(
        description="If True, reject trade intent if ATR is not ready (fail-closed)"
    )
    obi_missing_policy: Literal["neutral"] = Field(
        description="Policy when OBI is None: 'neutral' applies multiplier=1.0 (EXPLICIT, not silent)"
    )

    @model_validator(mode='after')
    def validate_clamp_order(self) -> 'EntryPlanConfig':
        """Ensure obi_mod_clamp_min <= 1.0 <= obi_mod_clamp_max."""
        if self.obi_mod_clamp_min > 1.0:
            raise ValueError(
                f"obi_mod_clamp_min ({self.obi_mod_clamp_min}) must be <= 1.0")
        if self.obi_mod_clamp_max < 1.0:
            raise ValueError(
                f"obi_mod_clamp_max ({self.obi_mod_clamp_max}) must be >= 1.0")
        if self.obi_mod_clamp_min > self.obi_mod_clamp_max:
            raise ValueError(
                f"obi_mod_clamp_min ({self.obi_mod_clamp_min}) must be <= obi_mod_clamp_max ({self.obi_mod_clamp_max})"
            )
        return self


class DecisionMakingDomainConfig(BaseModel):
    """Complete decision making domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    position_sizing: PositionSizingConfig = Field()

    # EP-01.2-INT: EntryPlan configuration for ATR-based SL/TP
    entry_plan: EntryPlanConfig = Field(
        description="EP-01.2: EntryPlan config for ATR-based entry/SL/TP computation"
    )
    qos: QosConfig = Field()
    features: FeaturesTtlConfig = Field()
    bar_gating: BarGatingConfig = Field()
    behavior_fsm: BehaviorFsmConfig = Field()
    risk_skew: RiskSkewConfig = Field()
    risk_gate: RiskGateConfig = Field()
    arming: ArmingConfig = Field()

    # DM-DIR-SSOT-STRICT-01: SSOT-required (no silent defaults)
    directional_sanity: DirectionalSanityConfig = Field()
    price_motion_sanity: PriceMotionSanityConfig = Field()
    flip: GlobalFlipKillswitchConfig = Field(
        ...,  # REQUIRED - no default
        description="Global FLIP killswitch. Per-symbol config in instruments.yaml."
    )

    # Optional hardening toggles (backward-compatible defaults)
    fail_closed_on_degraded_context: bool = Field(
        default=False,
        description=(
            "If true, DecisionMaking may DEFER intents when critical DecisionContext "
            "features are missing/invalid (fail-closed)."
        ),
    )
    degraded_context_critical_keys: List[str] = Field(
        default_factory=list,
        description=(
            "Optional global list of critical DecisionContext keys. If empty, DecisionMaking uses a safe built-in default set."
        ),
    )
    degraded_context_critical_keys_by_strategy: Dict[str, List[str]] = Field(
        default_factory=dict,
        description=(
            "Optional per-strategy overrides for degraded_context_critical_keys. "
            "If a strategy_id is present here, its list is used instead of the global list."
        ),
    )


# ============================================================================
# FEATURE ENGINEERING DOMAIN - Full Pydantic Validation
# ============================================================================

class EmaConfigDetailed(BaseModel):
    """EMA calculation configuration with validation."""
    model_config = ConfigDict(extra='forbid')

    period_short: int = Field(
        ge=1, le=50, description='Short EMA period (EMA3 default). Must be < period_long.')
    period_long: int = Field(
        ge=2, le=200, description='Long EMA period (EMA7 default). Must be > period_short.')

    @field_validator('period_long')
    @classmethod
    def validate_period_long_greater(cls, v: int, info) -> int:
        """Ensure period_long > period_short."""
        period_short = info.data.get('period_short', 3)
        if v <= period_short:
            raise ValueError(
                f"period_long ({v}) must be > period_short ({period_short})")
        return v


class VolumeConfigDetailed(BaseModel):
    """Volume metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')

    sma_length: int = Field(
        ge=2, le=100, description='SMA length for volume spike calculation')
    window_sec: int = Field(
        ge=1, le=3600, description='Volume aggregation window in seconds')
    min_window_volume_usd: float = Field(
        ge=0.0, description='Minimum volume threshold for active signal (Commit 6)')


class VolatilityConfigDetailed(BaseModel):
    """Volatility metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')

    sma_length: int = Field(
        ge=2, le=100, description='SMA length for volatility state calculation')
    window_sec: int = Field(
        ge=1, le=3600, description='Range window for volatility calculation in seconds')


class LiquidityConfigDetailed(BaseModel):
    """Liquidity metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')

    depth_half: float = Field(
        gt=0, le=1000000, description='Half-depth parameter for liquidity kappa and depth imbalance (USD)')
    kappa_min: float = Field(
        ge=0.0, le=1.0, description='Minimum liquidity kappa value')
    kappa_max: float = Field(
        ge=0.0, le=1.0, description='Maximum liquidity kappa value')

    @field_validator('kappa_max')
    @classmethod
    def validate_kappa_max(cls, v: float, info) -> float:
        """Ensure kappa_max >= kappa_min."""
        kappa_min = info.data.get('kappa_min', 0.3)
        if v < kappa_min:
            raise ValueError(
                f"kappa_max ({v}) must be >= kappa_min ({kappa_min})")
        return v


class EmaBiasConfig(BaseModel):
    """EMA bias calculation configuration with validation."""
    model_config = ConfigDict(extra='forbid')

    clamp_min: float = Field(
        ge=-1.0, le=0.0, description='Minimum clamp for EMA bias (typically -2%)')
    clamp_max: float = Field(
        ge=0.0, le=1.0, description='Maximum clamp for EMA bias (typically +2%)')

    @field_validator('clamp_max')
    @classmethod
    def validate_clamp_symmetry(cls, v: float, info) -> float:
        """Ensure clamp_max is positive opposite of clamp_min for symmetry."""
        clamp_min = info.data.get('clamp_min', -0.02)
        if abs(v + clamp_min) > 0.001:  # Allow small tolerance
            # Warning only, not an error - asymmetric is allowed
            pass
        return v


class VolumeSpikeConfig(BaseModel):
    """Volume spike calculation configuration with validation."""
    model_config = ConfigDict(extra='forbid')

    cap_max: float = Field(
        gt=1.0, le=10.0, description='Maximum cap for volume spike ratio (e.g., 3.0 = 300% of average)')
    sma_len: int = Field(
        ge=2, le=1000, description='SMA length for time-normalized volume rate samples')
    eps: float = Field(
        gt=0.0, le=1.0, description='Epsilon for spike denominator (avoid divide-by-zero)')


class VolumeZScoreConfig(BaseModel):
    """Volume Z-score configuration (FTR-03)."""
    model_config = ConfigDict(extra='forbid')

    clip_sigma: float = Field(
        gt=0.0,
        le=10.0,
        description='Clamp Z-score to [-clip_sigma, +clip_sigma] before tanh normalization'
    )


class LargeTradeImbalanceConfig(BaseModel):
    """Large trade imbalance configuration (TASK31)."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description="Enable large_trade_imbalance calculation and warmup blocking. If False, feature is treated as ready and value is neutral.",
    )
    window_ms: int = Field(
        ge=1000,
        le=600000,
        description="Window size in milliseconds for trade aggregation (must match market_data window for correctness)",
    )
    min_trades: int = Field(
        ge=1, le=100000, description="Minimum number of trades in window required to mark ready=true")
    eps: float = Field(
        gt=0.0, le=1.0, description="Epsilon for denominator guard (avoid divide-by-zero)")
    use_notional: bool = Field(
        description="If true, use notional (qty*price) instead of qty for imbalance")


class MacroSyncMetricsConfig(BaseModel):
    """Macro sync metrics configuration with validation."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        description='Enable macro sync correlation calculation')
    time_diff_threshold_ms: int = Field(
        ge=100, le=60000, description='Maximum time difference (ms) between ticks for return calculation')
    ttl_ms: int = Field(
        ge=100, le=600000, description='Anchor staleness TTL (ms). If anchor older than ttl_ms → macro_sync NOT_READY')
    min_buffer_size: int = Field(
        ge=2, le=100, description='Minimum buffer size before computing correlation')
    window: int = Field(
        ge=10, le=1000, description='Rolling window size for correlation calculation')
    bin_ms: int = Field(default=1000, ge=250, le=5000,
                        description='Time-grid bin size in ms for Macro Sync V2 alignment')
    max_gap_bins: int = Field(
        default=2, ge=0, le=120, description='Max consecutive missing bins allowed before NOT_READY (Macro Sync V2)')
    max_late_ms: int = Field(
        default=0,
        ge=0,
        le=60000,
        description="Late out-of-order tolerance (ms): if a tick falls behind last_bin_ts by <= max_late_ms, it is reordered/inserted; if larger, it is dropped (without forcing NOT_READY).",
    )
    eps: float = Field(default=1e-12, gt=0.0, le=1e-3,
                       description='Epsilon for sigma/variance guards (Macro Sync V2)')
    anchors: List[str] = Field(
        min_length=1, description='Anchor symbols for correlation (market leaders)')

    # P0-6 FIX: Add align_mode for length mismatch handling
    align_mode: str = Field(pattern='^(strict_len|tail_min_len)$',
                            description="Alignment mode: 'strict_len' (require exact match) or 'tail_min_len' (use shorter tail)")

    # P0-6 FIX: Add anchor_update_from_ticks to control double-update
    anchor_update_from_ticks: bool = Field(
        description='Update anchor buffers from symbol ticks (set false to avoid double-count when anchor is also trade symbol)')

    @field_validator('anchors')
    @classmethod
    def validate_anchors(cls, v: List[str]) -> List[str]:
        """Ensure anchors are valid symbol format."""
        for anchor in v:
            if not anchor.endswith("USDT"):
                raise ValueError(f"Anchor '{anchor}' must end with 'USDT'")
        return v


class VolatilityStateConfig(BaseModel):
    """Volatility state normalization configuration (P0-1 hardened).

    TASK-ZOMBIE-FIX: Removed dead fields (hard_floor_enabled, hist_floor_enabled, hist_floor_k_small).
    """
    model_config = ConfigDict(extra='forbid')

    cap_max: float = Field(
        gt=1.0, le=10.0, description='Maximum cap for volatility ratio normalization')
    tick_floor: float = Field(
        gt=0.0, description='Minimum floor in price units')
    division_eps: float = Field(
        gt=0.0, description='Epsilon for safe division')


class DepthImbalanceConfig(BaseModel):
    """Depth imbalance calculation configuration."""
    model_config = ConfigDict(extra='forbid')

    use_laplace_smoothing: bool = Field(
        description='Use Laplace smoothing (depth_half) in calculation')


class DeltaPriceConfig(BaseModel):
    """Delta price calculation configuration."""
    model_config = ConfigDict(extra='forbid')

    spike_filter_ms: int = Field(
        ge=100, le=3600000, description='Time gap (ms) above which delta_price is zeroed to filter spikes. Increase for backtest with larger bar intervals.')


class FeatureDefaultsConfig(BaseModel):
    """
    Default/neutral values for features.

    These values are returned when:
    - Insufficient data to compute feature
    - Division by zero would occur
    - Feature is in initialization phase

    All features are normalized to [0, 1] range, so 0.5 = neutral.
    """
    model_config = ConfigDict(extra='forbid')

    neutral_value: float = Field(
        ge=0.0, le=1.0, description='Default neutral value for all normalized features (0.5 = center of [0,1])')
    zero_value: float = Field(
        ge=0.0, le=1.0, description='Value for truly zero/absent features (absorption placeholder)')
    correlation_default: float = Field(
        ge=-1.0, le=1.0, description='Default correlation value when insufficient data')
    ms_per_sec: int = Field(
        ge=1000, le=1000, description='Milliseconds per second (constant for clarity)')


# ============================================================================
# P0-0: Readiness Contract Registry (SSOT)
# ============================================================================

class ReadinessRegistryConfig(BaseModel):
    """P0-0: Readiness contract registry - SSOT for declared ready keys."""
    model_config = ConfigDict(extra='forbid')

    declared_keys: List[str] = Field(
        min_length=1,
        description='All keys that FE can emit in warmup.ready. essential_features MUST be subset.'
    )


class WarmupEnforcementConfig(BaseModel):
    """P0-0: Warmup enforcement configuration. MANDATORY in production.

    TASK-ZOMBIE-FIX: Removed validate_essential_subset (dead, never read in runtime).
    """
    model_config = ConfigDict(extra='forbid')

    enforcement_mode: Literal["fail_fast", "warn_only", "disabled"] = Field(
        description='LOCKED to fail_fast in production. warn_only/disabled forbidden.'
    )
    # TASK-ZOMBIE-FIX: Removed validate_essential_subset (dead)
    check_full_ready_invariant: bool = Field(
        default=True,
        description='Invariant: full_ready=True ⇒ all declared_keys present'
    )

    @model_validator(mode="after")
    def _warn_if_not_fail_fast(self) -> "WarmupEnforcementConfig":
        if self.enforcement_mode != "fail_fast":
            import warnings
            warnings.warn(
                f"warmup.enforcement_mode={self.enforcement_mode} is NOT recommended for production. "
                "Use 'fail_fast' to ensure system does not trade until all features ready.",
                UserWarning
            )
        return self


# ============================================================================
# P0-2: Spread BPS Health Gate (Book Truth Validation)
# ============================================================================

class SpreadHealthGateConfig(BaseModel):
    """P0-2: Book health gate configuration for spread validation."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(description='Enable book health gate')
    max_age_sec: float = Field(
        gt=0.0, le=60.0,
        description='STEP 1: Hard fail if book older than this (seconds)'
    )
    min_update_events: int = Field(
        ge=0,
        description='STEP 2: Min book update events (any: qty/levels/price)'
    )
    min_trades_count: int = Field(
        ge=0,
        description='STEP 2: Min trades in window (OR with update_events)'
    )
    window_sec: float = Field(
        gt=0.0, le=300.0,
        description='Lookback window for counting events (seconds)'
    )


class SpreadBpsConfig(BaseModel):
    """P0-2: Spread BPS configuration with health gate."""
    model_config = ConfigDict(extra='forbid')

    health_gate: SpreadHealthGateConfig = Field(
        description='Book health gate settings')


# ============================================================================
# P0-3: Feature Sanity Firewall
# ============================================================================

class FeatureBoundsConfig(BaseModel):
    """Bounds for a single feature (min/max)."""
    model_config = ConfigDict(extra='forbid')

    min: float = Field(description='Minimum valid value')
    max: float = Field(description='Maximum valid value')


class FeatureSanityConfig(BaseModel):
    """P0-3: Feature sanity firewall configuration."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(description='Enable NaN/Inf/out-of-range firewall')
    nan_inf_behavior: Literal["neutral_and_not_ready", "neutral_only", "crash"] = Field(
        description='Behavior on NaN/Inf: neutral_and_not_ready=safe, crash=strict'
    )
    feature_bounds: Dict[str, FeatureBoundsConfig] = Field(
        description='Per-feature bounds (semantic validation)'
    )


# ============================================================================
# R1 (P1): Macro Resid — Beta-Adjusted Residual
# TASK-ZOMBIE-FIX: Removed MacroResidBoundsConfig (dead, feature_sanity.feature_bounds is SSOT)
# ============================================================================

class MacroResidConfig(BaseModel):
    """R1: Macro resid (beta-adjusted residual) configuration.

    Why: macro_sync (correlation-based) is UNSIGNED [0,1] → can't see SELL.
    macro_resid = r_asset - beta * r_btc → SIGNED, neutral=0, sees both directions.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description='Enable macro_resid computation (replaces macro_sync for direction)'
    )
    beta_window: int = Field(
        ge=10, le=500,
        description='Rolling window for beta calculation (samples)'
    )
    mad_window: int = Field(
        ge=5, le=200,
        description='Rolling window for MAD calculation (samples)'
    )
    winsor_percentile: float = Field(
        ge=0.0, le=0.25,
        description='Winsorize top/bottom percentile (e.g., 0.05 = 5%)'
    )
    var_floor: float = Field(
        gt=0.0,
        description='Floor for var(r_btc) to prevent div-by-zero'
    )
    scale_floor: float = Field(
        gt=0.0,
        description='Floor for MAD scale to prevent explosion'
    )
    clip: float = Field(
        gt=0.0,
        description='Output clip: |macro_resid| <= clip'
    )
    neutral: float = Field(
        default=0.0,
        description='SIGNED feature: neutral is 0.0'
    )
    # TASK-ZOMBIE-FIX: Removed bounds field (dead, feature_sanity.feature_bounds is SSOT)

    @model_validator(mode='after')
    def validate_windows(self) -> 'MacroResidConfig':
        """Validate window relationships."""
        if self.mad_window > self.beta_window:
            raise ValueError(
                f"mad_window ({self.mad_window}) cannot exceed beta_window ({self.beta_window})"
            )
        return self


# ============================================================================
# R2 (P2): Absorption — Experimental (Default OFF)
# ============================================================================

class AbsorptionProxyConfig(BaseModel):
    """R2: Absorption proxy configuration."""
    model_config = ConfigDict(extra='forbid')

    source: str = Field(
        description='Proxy source feature (NOT tfi - dedup required)'
    )
    window: int = Field(
        ge=5, le=500,
        description='Rolling window for proxy calculation (samples)'
    )
    eps: float = Field(
        gt=0.0,
        description='Epsilon for division safety'
    )

    @field_validator('source')
    @classmethod
    def source_not_tfi(cls, v: str) -> str:
        """Absorption proxy source cannot be 'tfi' (logical absurd)."""
        if v.lower() == 'tfi':
            raise ValueError(
                "Absorption proxy source cannot be 'tfi' (would be redundant)")
        return v


class AbsorptionDedupConfig(BaseModel):
    """R2: Absorption dedup guard against TFI."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description='Enable dedup guard (mute if correlated with TFI)'
    )
    window: int = Field(
        ge=10, le=500,
        description='Rolling correlation window (samples)'
    )
    threshold: float = Field(
        ge=0.0, le=1.0,
        description='If |corr(absorption, TFI)| > threshold → mute absorption'
    )


# TASK-ZOMBIE-FIX: Removed AbsorptionBoundsConfig (dead, feature_sanity.feature_bounds is SSOT)

class AbsorptionConfig(BaseModel):
    """R2: Absorption feature configuration (experimental, default OFF)."""
    model_config = ConfigDict(extra='forbid')

    mode: Literal["disabled", "proxy", "full"] = Field(
        description='Absorption mode: disabled (default), proxy, or full'
    )
    proxy: Optional[AbsorptionProxyConfig] = Field(
        default=None,
        description='Proxy config (required if mode=proxy)'
    )
    dedup: Optional[AbsorptionDedupConfig] = Field(
        default=None,
        description='Dedup guard config'
    )
    clip: float = Field(
        default=1.0, gt=0.0,
        description='Output clip: |absorption| <= clip'
    )
    neutral: float = Field(
        default=0.0,
        description='SIGNED feature: neutral is 0.0'
    )
    # TASK-ZOMBIE-FIX: Removed bounds field (dead, feature_sanity.feature_bounds is SSOT)

    @model_validator(mode='after')
    def validate_proxy_required(self) -> 'AbsorptionConfig':
        """Validate proxy config required when mode=proxy."""
        if self.mode == 'proxy' and self.proxy is None:
            raise ValueError("proxy config required when mode='proxy'")
        return self


class FeatureEngineeringDomainConfig(BaseModel):
    """
    Complete feature engineering domain configuration.

    All 9 features are configured here:
    - Base: OBI, TFI, delta_price, liquidity_kappa
    - Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
    """
    model_config = ConfigDict(extra='forbid')

    # TF-BAR-SSOT-002: enabled timeframes for feature calculation (mandatory, no defaults)
    enabled_timeframes_sec: List[int] = Field(
        min_length=1, description="Enabled timeframes in seconds for bar aggregation context")

    @field_validator('enabled_timeframes_sec')
    @classmethod
    def validate_timeframes(cls, v: List[int]) -> List[int]:
        if not all(60 <= tf <= 3600 for tf in v):
            raise ValueError(
                "All timeframes must be between 60 and 3600 seconds")
        if len(v) != len(set(v)):
            raise ValueError("Timeframes must be unique")
        return v

    # Master switch for Phase 1 metrics
    enable_new_metrics: bool = Field(
        description='Enable Phase 1 metrics (ema_bias, volume_spike, etc.)')

    # P0-5 FIX: Volume input mode for avoiding double-counting
    volume_input_mode: str = Field(pattern='^(integrate|sample_window_total)$',
                                   description="Volume input mode: 'integrate' (sum ticks) or 'sample_window_total' (treat tick as pre-windowed sample)")

    # Feature calculation configs
    ema: EmaConfigDetailed = Field()
    volume: VolumeConfigDetailed = Field()
    volatility: VolatilityConfigDetailed = Field()
    liquidity: LiquidityConfigDetailed = Field()

    # Normalization configs
    ema_bias: EmaBiasConfig = Field()
    volume_spike: VolumeSpikeConfig = Field()
    volume_zscore: VolumeZScoreConfig = Field()
    large_trade_imbalance: LargeTradeImbalanceConfig = Field()
    volatility_state: VolatilityStateConfig = Field()
    depth_imbalance: DepthImbalanceConfig = Field()
    delta_price: DeltaPriceConfig = Field()

    # Macro sync config
    macro_sync: MacroSyncMetricsConfig = Field()

    # Default/neutral values for edge cases
    defaults: FeatureDefaultsConfig = Field()

    # ════════════════════════════════════════════════════════════════════════════
    # P0-0: Readiness Contract Registry + Warmup Enforcement
    # ════════════════════════════════════════════════════════════════════════════
    readiness_registry: Optional[ReadinessRegistryConfig] = Field(
        default=None,
        description='P0-0: SSOT for declared ready keys. Required in production.'
    )
    warmup: Optional[WarmupEnforcementConfig] = Field(
        default=None,
        description='P0-0: Warmup enforcement. Required in production.'
    )

    # ════════════════════════════════════════════════════════════════════════════
    # P0-2: Spread BPS Health Gate
    # ════════════════════════════════════════════════════════════════════════════
    spread_bps: Optional[SpreadBpsConfig] = Field(
        default=None,
        description='P0-2: Spread health gate config. Required when spread_bps used.'
    )

    # ════════════════════════════════════════════════════════════════════════════
    # P0-3: Feature Sanity Firewall
    # ════════════════════════════════════════════════════════════════════════════
    feature_sanity: Optional[FeatureSanityConfig] = Field(
        default=None,
        description='P0-3: NaN/Inf/out-of-range firewall. Recommended for production.'
    )

    # ════════════════════════════════════════════════════════════════════════════
    # R1 (P1): Macro Resid — Beta-Adjusted Residual
    # ════════════════════════════════════════════════════════════════════════════
    macro_resid: Optional[MacroResidConfig] = Field(
        default=None,
        description='R1: Beta-adjusted residual (replaces macro_sync for direction). SIGNED, neutral=0.'
    )

    # ════════════════════════════════════════════════════════════════════════════
    # R2 (P2): Absorption — Experimental (Default OFF)
    # ════════════════════════════════════════════════════════════════════════════
    absorption: Optional[AbsorptionConfig] = Field(
        default=None,
        description='R2: Absorption feature (experimental). Default OFF, no live impact.'
    )

    def get_ema_alpha(self, period: str) -> float:
        """Calculate EMA alpha for given period."""
        if period == "short":
            n = self.ema.period_short
        else:
            n = self.ema.period_long
        return 2.0 / (n + 1)


# ============================================================================
# Risk Management Domain
# ============================================================================

class RiskScoreWeightsConfig(BaseModel):
    """Risk score weights configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    delta_price_pct: float = Field()
    obi: float = Field()
    tfi: float = Field()
    absorption_inverse: float = Field()


class TradingAllowedThresholdsConfig(BaseModel):
    """Trading allowed thresholds configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    # IMPORTANT: Default exists for test compatibility, but production MUST override
    max_risk_score: float = Field(
        description='Max risk score. PRODUCTION MUST OVERRIDE in domains.yaml!')


class RiskValidationConfig(BaseModel):
    """Risk validation configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    total_weight_min: float = Field()
    total_weight_max: float = Field()


class RiskManagementDomainConfig(BaseModel):
    """Complete risk management domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    risk_score_weights: RiskScoreWeightsConfig = Field()
    trading_allowed_thresholds: TradingAllowedThresholdsConfig = Field()
    validation: RiskValidationConfig = Field()

    # D5: Absorption deprecation flag
    # When False, absorption term is excluded from risk score calculation
    # NOTE: Other weights are NOT rescaled when absorption is disabled (per Plan v1)
    use_absorption_penalty: bool = Field(
        description='Whether to include absorption penalty in risk score. Set to False to disable deprecated absorption feature.')


# Position Tracking Domain
class PrecisionConfig(BaseModel):
    """Position precision configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    quantity_min_threshold: float = Field()
    flat_position_threshold: float = Field()
    decimal_places: int = Field()


# TASK-ZOMBIE-FIX: Removed ThreadTimeoutsConfig class (dead, join_timeout_sec never read in runtime)


class PositionTrackingDomainConfig(BaseModel):
    """Complete position tracking domain configuration.

    TASK-ZOMBIE-FIX: Removed thread_timeouts (dead, never read in runtime).
    """
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    precision: PrecisionConfig = Field()
    # TASK-ZOMBIE-FIX: Removed thread_timeouts (dead)
    positions_stale_ttl_sec: int = Field(
        description='Portfolio freshness TTL for AuroraBridge gate')
    enable_market_tick_subscription: bool = Field(
        description='Enable EVT:MARKET_TICK_RECEIVED subscription for mark-price PnL (optional)')


# NOTE: AccountObserverDomainConfig removed (TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)
# AccountObserver was Legacy Spot code, system now uses Futures-only via ExecPosFSM.


# Execution Position Domain
class ExposureGuardConfig(BaseModel):
    """Exposure guard configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    pending_ttl_sec: int = Field()
    post_fill_ttl_sec: int = Field()
    stale_ttl_sec: int = Field()
    max_equity_utilization_pct: float = Field()
    max_portfolio_fraction: float = Field()
    max_long_utilization_pct: float = Field()
    max_short_utilization_pct: float = Field()
    max_directional_ratio: float = Field()
    max_concentration_pct: float = Field()
    # PURGE-DEAD-CONFIG-03: pending_timeout_sec removed (never read in runtime)


class FsmOpenConfig(BaseModel):
    """FSM open configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    idempotency_window_sec: int = Field()


class OrderIndexConfig(BaseModel):
    """Order index configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    ttl_sec: int = Field()


class MetricsCollectorConfig(BaseModel):
    """Metrics collector configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    window_size_minutes: int = Field()
    recent_rejections_minutes: int = Field()


class IdempotentCancelConfig(BaseModel):
    """Idempotent cancel configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    max_retries: int = Field()


class ExecutionUtilsConfig(BaseModel):
    """Execution utilities configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    client_order_id_max_length: int = Field()
    basis_points_base: float = Field()


class InflightReconcileConfig(BaseModel):
    """In-flight order reconciliation configuration (ExecutionPosition domain)."""
    model_config = ConfigDict(extra='forbid')

    inflight_ttl_sec: int = Field(
        description="TTL before reconciliation check (seconds)")
    max_ttl_sec: int = Field(
        description="Force-clear after this TTL (seconds)")
    reconcile_interval_sec: int = Field(
        description="Interval between reconcile attempts (seconds)")
    # PURGE-DEAD-CONFIG-03: reconcile_retries/reconcile_backoff_ms removed (retry logic not implemented)
    verbose_logging: bool = Field(description="Log reconciliation details")


class EventDedupConfig(BaseModel):
    """FSM event deduplication configuration (bounded memory)."""
    model_config = ConfigDict(extra='forbid')

    max_size: int = Field(
        default=100000, description="Max number of events to track")
    ttl_ms: int = Field(
        default=86400000, description="Event TTL in milliseconds (24h)")


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
        description="Enable per-timeframe pending entry TTL (if False, uses global watchdog fill_ttl_ms)"
    )
    ttl_by_tf_sec: Dict[int, int] = Field(
        description=(
            "Map of timeframe_seconds -> entry_ttl_seconds. "
            "E.g. {180: 45, 300: 60, 900: 180} means 3m bars get 45s TTL, 5m get 60s, 15m get 180s."
        )
    )
    reject_unknown_tf: bool = Field(
        description="If True (fail-closed), reject entry if tf_sec not in ttl_by_tf_sec map"
    )
    cancel_on_regime_change: bool = Field(
        description="Cancel pending entry when EVT:REGIME_DETECTED indicates regime changed"
    )
    cancel_on_supersede: bool = Field(
        description="Cancel old pending entry when new open request arrives for same symbol"
    )
    cancel_on_panic: bool = Field(
        description="Cancel pending entry immediately when panic_killswitch is activated"
    )
    # DET-BT-13-FIX: Explicit timeout for supersede cancel wait (STRICT SSOT)
    supersede_cancel_timeout_sec: float = Field(
        ...,
        ge=1.0, le=60.0,
        description="Timeout (seconds) to wait for supersede cancel confirmation before forcing new open. Explicit config required."
    )

    @model_validator(mode='after')
    def validate_ttl_values(self) -> 'PendingEntryTTLConfig':
        """Ensure all TTL values are positive and tf_sec >= 60."""
        for tf_sec, ttl_sec in self.ttl_by_tf_sec.items():
            if tf_sec < 60:
                raise ValueError(f"tf_sec must be >= 60, got {tf_sec}")
            if ttl_sec <= 0:
                raise ValueError(
                    f"TTL must be > 0, got {ttl_sec} for tf_sec={tf_sec}")
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
        default=False,
        description="Enable maker-only enforcement for entry LIMIT orders"
    )
    # PURGE-DEAD-CONFIG-03: tif_value removed (always GTX, hardcoded in fsm_open.py)
    # PURGE-DEAD-CONFIG-03: reject_on_fail removed (always True, no fallback by design)


class OrderCapabilitiesConfig(BaseModel):
    """ORDER-POLICY-01: Supported order types and TIF values for the execution layer.

    This is SSOT for what the system can process. Strategy policies must be
    a subset of these capabilities.
    """
    model_config = ConfigDict(extra='forbid')

    supported_order_types: List[Literal["LIMIT", "MARKET"]] = Field(
        ...,
        min_length=1,
        description="Allowed order types. No defaults - must be explicitly configured."
    )
    supported_tif: List[Literal["GTC", "GTX", "IOC", "FOK"]] = Field(
        ...,
        min_length=1,
        description="Allowed time-in-force values. No defaults - must be explicitly configured."
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
        default=20,
        ge=1, le=500,
        description="First retry: widen TP by N basis points (20 = 0.2%). Handles most -2021 cases."
    )
    tp_widen_second_bps: int = Field(
        default=50,
        ge=1, le=500,
        description="Second retry: widen TP by N basis points (50 = 0.5%). Handles volatile markets."
    )
    retry_backoff_ms: List[int] = Field(
        default=[200, 400],
        min_length=1, max_length=5,
        description="Backoff delays between retries (ms). [200, 400] = exponential backoff."
    )


class OrderLifecycleConfig(BaseModel):
    """MAGIC-NUM-EXTRACTION: Order lifecycle timing configuration.

    Settlement delays are required because:
    - fill_settlement_delay_ms: REST API lag after MARKET fill before position updates
    - position_close_cleanup_delay_ms: Exchange-side settlement after CLOSE before orphan cleanup
    """
    model_config = ConfigDict(extra='forbid')

    fill_settlement_delay_ms: int = Field(
        default=500,
        ge=100, le=5000,
        description="Delay after fill before bracket placement (REST API lag). 500ms typical for Binance Futures."
    )
    position_close_cleanup_delay_ms: int = Field(
        default=2000,
        ge=500, le=10000,
        description="Delay after CLOSE before orphan bracket cleanup. Exchange-side settlement time."
    )


class ShadowCheckConfig(BaseModel):
    """MAGIC-NUM-EXTRACTION: Shadow notional exposure check configuration.

    Periodic check comparing FSM-tracked exposure vs exchange-reported positions.
    Detects drift between internal state and exchange reality.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description="Enable periodic shadow exposure checks."
    )
    check_every_n_requests: int = Field(
        default=10,
        ge=1, le=100,
        description="Run shadow check every N exposure requests (sampling rate)."
    )
    tolerance_pct: float = Field(
        default=1.0,
        ge=0.1, le=10.0,
        description="Allowed mismatch percentage before warning (1.0 = 1%)."
    )
    absolute_threshold_usd: float = Field(
        default=5000.0,
        ge=100.0, le=1000000.0,
        description="Absolute mismatch threshold in USD (for large portfolios)."
    )
    use_absolute_for_large_portfolios: bool = Field(
        default=True,
        description="Use absolute threshold for portfolios above large_portfolio_threshold_usd."
    )
    large_portfolio_threshold_usd: float = Field(
        default=1000000.0,
        ge=10000.0,
        description="Portfolio value above which to use absolute threshold."
    )


class GuardianConfig(BaseModel):
    """OrderGuardian configuration (already partially in use, completing extraction)."""
    model_config = ConfigDict(extra='forbid')

    poll_interval_ms: int = Field(
        ...,
        ge=100, le=5000,
        description="Polling interval for OrderGuardian reconciliation loop."
    )
    unified: bool = Field(
        default=True,
        description="Use unified guardian mode (single reconcile loop for all symbols)."
    )
    emit_tidy_event: bool = Field(
        default=True,
        description="Emit EVT:SYMBOL_TIDY after successful orphan cleanup."
    )
    cleanup_ttl_ms: int = Field(
        default=6000,
        ge=1000, le=60000,
        description="TTL before considering an orphaned bracket for cleanup."
    )
    symbol_cooldown_ms: int = Field(
        default=4000,
        ge=1000, le=60000,
        description="Cooldown after symbol tidy before next cleanup attempt."
    )


class BracketHealthCheckConfig(BaseModel):
    """BRACKET-HEALTH: Periodic safety net for missing SL/TP brackets on open positions."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description="Enable periodic bracket health check loop."
    )
    interval_sec: int = Field(
        ...,
        ge=30, le=300,
        description="Seconds between health check cycles."
    )
    grace_period_ms: int = Field(
        ...,
        ge=5000,
        description="Milliseconds after position open before checking brackets."
    )
    max_placements_per_cycle: int = Field(
        default=2,
        ge=1, le=10,
        description="Max bracket placements per cycle (API rate limiting)."
    )


class QuietHoursConfig(BaseModel):
    """Quiet hours gate: block new OPEN entries during configured UTC time windows."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=False,
        description="Enable quiet hours gate. When True, new entries are blocked during configured windows."
    )
    windows: List[str] = Field(
        default_factory=list,
        description='UTC time windows in "HH:MM-HH:MM" format. Wraps around midnight.'
    )


class ExecutionPositionDomainConfig(BaseModel):
    """Complete execution position domain configuration."""
    model_config = ConfigDict(extra='forbid')  # CANONICAL: strict validation

    # P1-CONFIG-EXTRACTION: Fallback mode configuration (fail-closed)
    fallback: FallbackConfig = Field(
        description="P1: Fallback mode config (policy, risk_reduction_pct, backoff_ms)"
    )
    # TASK-ZOMBIE-FIX: Removed duplicate watchdog (FSM reads from trading.execution.watchdog)
    exposure_guard: ExposureGuardConfig = Field()
    fsm_open: FsmOpenConfig = Field()
    order_index: OrderIndexConfig = Field()
    inflight_reconcile: InflightReconcileConfig = Field()
    metrics_collector: MetricsCollectorConfig = Field()
    idempotent_cancel: IdempotentCancelConfig = Field()
    utils: ExecutionUtilsConfig = Field()
    event_dedup: Optional[EventDedupConfig] = Field(
        default=None, description="Event deduplication config")
    # EP-01.3-INT: Per-timeframe pending entry TTL
    pending_entry_ttl: PendingEntryTTLConfig = Field(
        description="EP-01.3: Per-timeframe TTL for pending LIMIT entry orders"
    )
    # EP-01.4-INT-B: Maker-only (post-only) entry configuration
    maker_only_entry: MakerOnlyEntryConfig = Field(
        default_factory=MakerOnlyEntryConfig,
        description="EP-01.4: Maker-only (GTX) entry order configuration"
    )
    # ORDER-POLICY-01: Global order capabilities (SSOT)
    order_capabilities: OrderCapabilitiesConfig = Field(
        description="ORDER-POLICY-01: Supported order types and TIF for the exchange adapter"
    )
    # MAGIC-NUM-EXTRACTION: Bracket placement retry configuration
    bracket_placement: BracketPlacementConfig = Field(
        default_factory=BracketPlacementConfig,
        description="TP/SL bracket placement retry config for -2021 error handling"
    )
    # MAGIC-NUM-EXTRACTION: Order lifecycle timing configuration
    order_lifecycle: OrderLifecycleConfig = Field(
        default_factory=OrderLifecycleConfig,
        description="Settlement delays and preflight timing for order lifecycle"
    )
    # MAGIC-NUM-EXTRACTION: Shadow exposure check configuration
    shadow_check: ShadowCheckConfig = Field(
        default_factory=ShadowCheckConfig,
        description="Periodic shadow notional exposure validation"
    )
    # MAGIC-NUM-EXTRACTION: OrderGuardian configuration
    guardian: GuardianConfig = Field(
        default_factory=GuardianConfig,
        description="OrderGuardian polling and cleanup configuration"
    )
    # BRACKET-HEALTH: Periodic bracket health check (safety net)
    bracket_health_check: Optional[BracketHealthCheckConfig] = Field(
        default=None,
        description="Safety net: periodic check for missing SL/TP on open positions"
    )
    # QUIET-HOURS: Block new entries during configured UTC time windows
    quiet_hours: QuietHoursConfig = Field(
        default_factory=QuietHoursConfig,
        description="Quiet hours: block new entries during configured UTC time windows"
    )


class DomainsDebugConfig(BaseModel):
    """Debug / shadow-only switches for domain gates (fail-closed in live/prod)."""
    model_config = ConfigDict(extra='forbid')

    disable_positions_stale_gate: bool = Field(
        description="DEV/SHADOW ONLY: disables position stale TTL gate (AuroraBridge portfolio freshness)."
    )
    disable_daily_loss_limit: bool = Field(
        description="DEV/SHADOW ONLY: disables daily loss/drawdown gate (RiskManagement DailyRiskState)."
    )


# Top-Level Domains Configuration
class DomainsConfig(BaseModel):
    """Top-level domains configuration container (CANONICAL)."""
    model_config = ConfigDict(
        extra='forbid')  # CANONICAL: strict validation, fail-fast on unknown fields

    debug: DomainsDebugConfig = Field()
    decision_making: DecisionMakingDomainConfig = Field()
    feature_engineering: FeatureEngineeringDomainConfig = Field()
    risk_management: RiskManagementDomainConfig = Field()
    position_tracking: PositionTrackingDomainConfig = Field()
    # NOTE: account_observer removed (TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)
    execution_position: ExecutionPositionDomainConfig = Field()


# ============================================================================
# Aurora Per-Instrument Configuration (Phase 0)
# ============================================================================

class AuroraSideBiasConfig(BaseModel):
    """Aurora side bias configuration per instrument."""
    model_config = ConfigDict(extra='forbid')

    penalty_factor: Optional[float] = Field(
        description='Penalty multiplier for counter-bias trades')
    window_sec: Optional[int] = Field(
        description='Rolling window in seconds for side bias calculation')
    target_ratio: Optional[float] = Field(
        description='Target long/short ratio (e.g., 0.5 = balanced)')


class RegimeTpSlConfig(BaseModel):
    """
    Regime-based TP/SL configuration for Aurora strategy.

    AURORA_REGIME_TP_SL_PLAN: Дозволяє адаптувати SL/TP залежно від режиму ринку.

    Modes:
    - "pct_mult": Мультиплікатори до базових sl_pct/tp_low_ratio
    - "atr": ATR-based розрахунок (потребує atr feature)

    При enabled=false поведінка повністю як раніше.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=False,
        description='Enable regime-based TP/SL. False = legacy behavior.'
    )
    mode: Literal["pct_mult", "atr"] = Field(
        default="pct_mult",
        description='Calculation mode: pct_mult (simple) or atr (volatility-based)'
    )

    # === pct_mult mode: multipliers ===
    sl_mult: Dict[str, float] = Field(
        default_factory=lambda: {"DEFAULT": 1.0},
        description='SL multiplier per regime (requires DEFAULT key)'
    )
    tp_mult: Dict[str, float] = Field(
        default_factory=lambda: {"DEFAULT": 1.0},
        description='TP RR multiplier per regime (requires DEFAULT key)'
    )

    # === atr mode: ATR-based coefficients ===
    sl_k_atr: Optional[Dict[str, float]] = Field(
        default=None,
        description='SL as k×ATR% per regime (atr mode only)'
    )
    rr_by_regime: Optional[Dict[str, float]] = Field(
        default=None,
        description='Risk-reward ratio per regime (atr mode only)'
    )

    # === Guardrails ===
    # NOTE: All guardrails use CLAMP behavior (not fail-closed).
    # Values outside range are clamped to min/max, not rejected.
    min_sl_pct: float = Field(
        default=0.003,
        description='Min SL% (0.3%) - clamp up if below'
    )
    max_sl_pct: float = Field(
        default=0.06,
        description='Max SL% (6%) - clamp down if above'
    )
    min_tp_rr: float = Field(
        default=0.3,
        description='Min TP RR ratio - clamp up if below'
    )
    max_tp_rr: float = Field(
        default=3.0,
        description='Max TP RR ratio - clamp down if above'
    )
    min_dist_bps: int = Field(
        default=15,
        description='Min distance in bps from entry to SL/TP - FAIL-CLOSED if below (cannot clamp)'
    )

    @model_validator(mode='after')
    def validate_default_keys(self) -> 'RegimeTpSlConfig':
        """Fail-closed: DEFAULT key is mandatory in mult dicts."""
        if self.mode == "pct_mult":
            if 'DEFAULT' not in self.sl_mult:
                raise ValueError(
                    "regime_tpsl.sl_mult must contain 'DEFAULT' key")
            if 'DEFAULT' not in self.tp_mult:
                raise ValueError(
                    "regime_tpsl.tp_mult must contain 'DEFAULT' key")
        elif self.mode == "atr":
            if self.sl_k_atr is None or 'DEFAULT' not in self.sl_k_atr:
                raise ValueError(
                    "regime_tpsl.sl_k_atr must contain 'DEFAULT' key for atr mode")
            if self.rr_by_regime is None or 'DEFAULT' not in self.rr_by_regime:
                raise ValueError(
                    "regime_tpsl.rr_by_regime must contain 'DEFAULT' key for atr mode")
        return self


class AuroraExitConfig(BaseModel):
    """Aurora exit/stop-loss configuration per instrument."""
    model_config = ConfigDict(extra='forbid')

    sl_pct: Optional[float] = Field(
        description='Stop-loss as percentage from entry (e.g., 0.005 = 0.5%)')
    max_hold_sec: Optional[int] = Field(
        description='Maximum position hold time in seconds')
    regime_tpsl: Optional[RegimeTpSlConfig] = Field(
        default=None,
        description='Regime-based TP/SL config (AURORA_REGIME_TP_SL_PLAN)'
    )


class AuroraTakeProfitConfig(BaseModel):
    """Aurora take-profit configuration per instrument."""
    model_config = ConfigDict(extra='forbid')

    tp_low_ratio: Optional[float] = Field(
        description='TP1 as ratio to ATR or fixed percent')
    tp_high_ratio: Optional[float] = Field(
        description='TP2 as ratio to ATR or fixed percent')
    partial_exit_pct: Optional[float] = Field(
        description='Percentage to exit at TP1 (e.g., 0.7 = 70%)')


class AuroraTrailingStopConfig(BaseModel):
    """Aurora trailing stop configuration per instrument."""
    model_config = ConfigDict(extra='forbid')

    enabled: Optional[bool] = Field(description='Enable trailing stop')
    activation_pct: Optional[float] = Field(
        description='Activate trailing after this profit % (e.g., 0.003 = 0.3%)')
    trail_pct: Optional[float] = Field(
        description='Trail distance as % from high-water mark')
    min_update_interval_sec: Optional[int] = Field(
        description='Minimum seconds between SL updates (rate limit)')


class AuroraExecutionConfig(BaseModel):
    """Aurora execution-specific configuration per instrument."""
    model_config = ConfigDict(extra='forbid')

    order_type: Optional[str] = Field(description='Order type: LIMIT, MARKET')
    post_only: Optional[bool] = Field(
        description='Use post-only orders for maker fees')
    max_slippage_bps: Optional[int] = Field(
        description='Max allowed slippage in basis points')


# ============================================================================
# PHASE 3+ Per-Instrument Override Config Classes
# ============================================================================

class EmaClampConfig(BaseModel):
    """Per-asset EMA clamp range override (Phase 3+)."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(description='Enable per-asset clamp override')
    clamp_min: Optional[float] = Field(
        description='Override global ema_bias.clamp_min')
    clamp_max: Optional[float] = Field(
        description='Override global ema_bias.clamp_max')


class SignalThresholdConfig(BaseModel):
    """Per-asset signal threshold override (Phase 3+)."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(description='Enable per-asset threshold override')
    value: Optional[float] = Field(
        description='Override global signal_threshold')


class MaxRiskScoreConfig(BaseModel):
    """Per-asset max risk score override (Phase 3+)."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        description='Enable per-asset max_risk_score override')
    value: Optional[float] = Field(
        description='Max risk score threshold for entry filtering')

    @model_validator(mode="after")
    def _validate_enabled_requires_value(self) -> "MaxRiskScoreConfig":
        # MR-RISK-GATE-NONE-FIX-01: never allow enabled override with null value.
        # Inherit is expressed by omitting the override field entirely.
        if self.enabled and self.value is None:
            raise ValueError(
                "max_risk_score.enabled=true requires max_risk_score.value (omit override to inherit)")
        return self


class VolatilityEntryConfig(BaseModel):
    """Volatility-based limit entry pricing (Maker/GTX compliance).

    Calculates entry price offset: LimitPrice = AnchorPrice ± (ATR × RegimeMultiplier).
    - LONG/BUY: entry_price = anchor_price - offset (bid below)
    - SHORT/SELL: entry_price = anchor_price + offset (ask above)

    STRICT: Requires 'atr' feature from FeatureEngineering. No fallbacks.
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True, description="Enable volatility-based entry pricing")
    regime_multipliers: Dict[str, float] = Field(
        description="Regime → multiplier. MUST include 'DEFAULT' key (fail-closed)."
    )

    @model_validator(mode='after')
    def validate_default_exists(self) -> 'VolatilityEntryConfig':
        """Fail-closed: DEFAULT key is mandatory."""
        if 'DEFAULT' not in self.regime_multipliers:
            raise ValueError(
                "volatility_entry_logic.regime_multipliers must contain 'DEFAULT' key (fail-closed)"
            )
        return self


# Canonical feature keys for per-asset signal weights (TASK54: Weight Key Fix)
# These MUST match the feature names emitted by FeatureEngineering
# R1: macro_resid added, macro_sync deprecated but kept for backward compat
CANONICAL_WEIGHT_KEYS = frozenset({
    "obi", "tfi", "delta_price", "ema_bias", "volume_spike",
    "volatility_state", "depth_imbalance",
    "macro_sync",   # DEPRECATED: kept for backward compat, use macro_resid
    "macro_resid",  # R1: Beta-adjusted residual (SIGNED, neutral=0)
    # liquidity_kappa REMOVED: Moved to LiquidityGateConfig
})


class AuroraInstrumentConfig(BaseModel):
    """
    Complete per-instrument configuration for Aurora strategy.

    Fallback chain:
    1. strategies.aurora.assets.<SYMBOL>.<param> (this config)
    2. strategies.aurora.decision.<param> (global fallback)
    """
    model_config = ConfigDict(
        extra='forbid')  # Strict validation (CFG-AURORA-INSTRUMENTS-SSOT-01)

    # Strategy enable/disable flag
    enabled: bool = Field(
        description='Enable Aurora strategy for this instrument (default: True for backward compat)')

    # Signal weights (Phase 3+ Optuna results)
    weights: Optional[Dict[str, float]] = Field(
        default=None, description='Per-feature signal weights from Optuna')

    @field_validator('weights', mode='before')
    @classmethod
    def validate_weight_keys(cls, v):
        """TASK54: Fail-closed validation of weight keys to prevent silent signal_score bugs."""
        if v is None:
            return v
        if not isinstance(v, dict):
            return v
        invalid_keys = set(v.keys()) - CANONICAL_WEIGHT_KEYS
        if invalid_keys:
            raise ValueError(
                f"Invalid weight keys: {sorted(invalid_keys)}. "
                f"Valid canonical keys: {sorted(CANONICAL_WEIGHT_KEYS)}. "
                f"(TASK54: Weight Key Mismatch Fix)"
            )
        return v

    # Side bias
    side_bias: Optional[AuroraSideBiasConfig] = Field(
        default=None, description='Side bias configuration')

    # Position mode
    position_mode: Optional[Literal["STRICT", "DYNAMIC"]] = Field(
        default=None, description='STRICT = No pyramiding (1 trade only), DYNAMIC = Pyramiding allowed up to cap')

    # P1: Active Leverage Management - per-symbol leverage override
    leverage: Optional[LeverageConfig] = Field(
        default=None, description='Per-symbol leverage settings (P1: Active Leverage)')

    # Regime-based thresholds
    regime_thresholds: Optional[Dict[str, float]] = Field(
        default=None, description='Threshold multipliers per regime (TREND, VOLATILE, FLAT)')

    # Regime-based position sizing
    regime_sizing: Optional[Dict[str, float]] = Field(
        default=None, description='Position size multipliers per regime')

    # Exit configuration
    exit: Optional[AuroraExitConfig] = Field(
        default=None, description='Stop-loss and max hold time')

    # Take profit configuration
    take_profit: Optional[AuroraTakeProfitConfig] = Field(
        default=None, description='TP1/TP2 partial exit settings')

    # Trailing stop configuration
    trailing_stop: Optional[AuroraTrailingStopConfig] = Field(
        default=None, description='Trailing stop settings')

    # PURGE-04: execution and ema_clamp fields removed (dead code)

    # Phase 3+ per-asset overrides
    signal_threshold: Optional[SignalThresholdConfig] = Field(
        default=None, description='Per-asset signal threshold (Phase 3+)')
    max_risk_score: Optional[MaxRiskScoreConfig] = Field(
        default=None,
        description='Per-asset max risk score (Phase 3+)',
    )

    cooldown_sec: Optional[int] = Field(
        default=None, description='Per-instrument cooldown in seconds (overrides global qos.symbol_cooldown_sec)')

    # Phase 3+ Recovery: Regime gating
    allowed_regimes: Optional[List[str]] = Field(
        default=None, description='If set, only trade when current regime is in this list (Phase 3+ regime gating)')

    # Phase 4: Score V2 Overrides
    scoring_version: Optional[Literal["v1", "v2"]] = Field(
        default=None, description="Override scoring version")
    feature_neutrals: Optional[Dict[str, float]] = Field(
        default=None, description="Override neutral offsets")
    essential_features: Optional[List[str]] = Field(
        default=None, description="Override essential features list")
    liquidity_gate: Optional[LiquidityGateConfig] = Field(
        default=None, description="Override liquidity gate")

    # Anti-Churn Gate: Per-symbol holding period override
    holding_period: Optional[HoldingPeriodConfig] = Field(
        default=None, description="Per-symbol holding period override (RFC: docs/RFC_min_duration_logic.md)")

    # Re-entry Cooldown: Per-symbol re-entry cooldown override
    reentry_cooldown_sec: Optional[int] = Field(
        default=None, description="Per-symbol re-entry cooldown override (seconds)")

    # Phase 1.5 Recovery: Per-instrument timeframe
    timeframe_sec: Optional[int] = Field(
        default=None, description='Bar timeframe in seconds for this instrument. SOL=180 (3m), BTC/ETH=300 (5m)')

    # Smart Limit Entry: Volatility-based pricing
    volatility_entry_logic: Optional[VolatilityEntryConfig] = Field(
        default=None, description='Volatility-based limit entry pricing (Maker/GTX compliance)')

    @model_validator(mode="before")
    @classmethod
    def _reject_null_inherit_sentinels(cls, data):
        # MR-RISK-GATE-NONE-FIX-01: "inherit" must not be expressed via `max_risk_score: null`.
        # Omit the key entirely to inherit global behavior.
        if isinstance(data, dict) and "max_risk_score" in data and data["max_risk_score"] is None:
            raise ValueError(
                "max_risk_score must be omitted to inherit; explicit null is forbidden")
        return data

    @model_serializer(mode="wrap")
    def _serialize(self, handler):
        data = handler(self)
        if isinstance(data, dict) and data.get("max_risk_score") is None:
            data.pop("max_risk_score", None)
        return data


class StrategyExecutionConfig(BaseModel):
    """Execution policy for strategies (ORDER-POLICY-01)."""
    model_config = ConfigDict(extra='forbid')

    entry_order_type: Literal["LIMIT", "MARKET"] = Field(...)
    entry_tif: Optional[Literal["GTC", "GTX", "IOC", "FOK"]] = Field(
        default=None,
        description="Time-in-force for LIMIT orders. Required for LIMIT, None for MARKET."
    )


class AuroraStrategyConfig(BaseModel):
    """Aurora strategy SSOT config (strategy profile: config/aurora/strategies/aurora.yaml).

    Contract:
    - Global policy lives in `aurora.decision` (validated as DecisionConfig)
    - Per-asset overrides live in `aurora.assets.<SYMBOL>` (validated as AuroraInstrumentConfig)
    """
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(description="Enable Aurora strategy globally")
    type: str = Field(description="Strategy type identifier (informational)")
    description: str = Field(
        description="Human description of the strategy profile")
    timeframe_sec: int = Field(
        ge=60, le=3600, description='Bar timeframe in seconds')

    # ORDER-POLICY-01: Execution policy
    execution: StrategyExecutionConfig = Field(
        description="Execution policy (SSOT)")

    # DM-SAFETY-BYPASSES-P1: Safety gates configuration
    safety_gates: SafetyGatesConfig = Field(
        description="Safety gates control (directional/price motion gates)"
    )

    # SCORCHED-EARTH-2026-01-27: legacy_tick_path_enabled DELETED
    # Migration to AuroraHandler complete. Always using new architecture.

    # Phase 3: Shadow mode for kernel validation.
    # When enabled, legacy path also calls the kernel and logs divergences (no side effects).
    shadow_mode_enabled: bool = Field(
        default=False,
        description="Enable shadow mode: compare legacy scoring with kernel and log divergences",
    )

    # Global defaults / policy for Aurora decision-making.
    decision: DecisionConfig = Field(
        description="Aurora decision policy (global defaults)")

    # Per-symbol overrides (formerly aurora_instruments.yaml).
    assets: Dict[str, AuroraInstrumentConfig] = Field(
        description="Per-symbol Aurora overrides (symbol -> config)")


class StrategiesConfig(BaseModel):
    """Canonical strategy policy namespace (CFG-STRATEGY-SSOT-FREEZE-03)."""

    model_config = ConfigDict(extra="forbid")

    aurora: Optional[AuroraStrategyConfig] = Field(
        default=None,
        description="Aurora strategy config (from strategies/aurora.yaml)",
    )
    mean_reversion: Optional[MeanReversion1mStrategyConfig] = Field(
        default=None,
        description="Mean Reversion 1m strategy config (from strategies/mean_reversion.yaml)",
    )


class OpsConfig(BaseModel):
    """Operations configuration (killswitch, quiet hours, monitoring).
    """
    model_config = ConfigDict(extra='forbid')

    # Emergency controls (A-01 fix)
    panic_killswitch: bool = Field(
        description='Emergency kill switch - blocks all new CMD:OPEN when True')

    # Used in tooling only
    metrics_url: Optional[str] = Field(
        default=None,
        description='Metrics endpoint (tooling only)'  # Used in tooling only
    )
    reports_dir: Optional[str] = Field(
        default=None,
        # Used in tooling only
        description='Reports output directory (tooling only)'
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
        description="Market data source mode (should be 'live' for real prices)")
    feature_engineering: DomainModeConfig = Field(
        description='Feature engineering mode (should match market_data)')
    decision_making: DomainModeConfig = Field(
        description='Decision making mode (should match market_data)')
    # PURGE-DIRTY-DOZEN: Made optional (dead, global trading_mode is SSOT) - 2026-01-25
    risk_management: Optional[DomainModeConfig] = Field(
        default=None, description='DEPRECATED: Use global trading_mode')
    execution_position: Optional[DomainModeConfig] = Field(
        default=None, description='DEPRECATED: Use global trading_mode')
    audit_trail: Optional[DomainModeConfig] = Field(
        default=None, description='DEPRECATED: Use global trading_mode')


class BacktestConfig(BaseModel):
    """Configuration for Backtest Execution Mode."""
    model_config = ConfigDict(extra='forbid')

    start_date: str = Field(description="Backtest start date (YYYY-MM-DD)")
    end_date: str = Field(description="Backtest end date (YYYY-MM-DD)")
    initial_balance: float = Field(
        default=10000.0, description="Initial USDT balance")


# SCORCHED-EARTH-2026-01-27: Typed TCAPrefsConfig (was Dict[str, Any])
class TCAPrefsConfig(BaseModel):
    """Transaction Cost Analysis (TCA) preferences."""
    model_config = ConfigDict(extra='forbid')

    max_slippage_pct: float = Field(
        default=0.5, description="Max allowed slippage %")
    max_slippage_bps: int = Field(
        default=10, description="Max allowed slippage in basis points")
    max_latency_ms: int = Field(
        default=500, description="Max allowed latency (intent to filled) in ms")
    maker_preference: Literal["maker", "taker", "neutral", "any"] = Field(
        default="neutral",
        description="Execution preference (maker/taker/neutral)"
    )
    preferred_venue: str = Field(
        default="binance", description="Preferred execution venue")
    execution_priority: Literal["speed", "price", "balanced"] = Field(
        default="speed",
        description="Execution priority: speed (market) vs price (limit)"
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


class TradingConfig(BaseModel):
    """Main trading configuration (with mode overrides)."""
    model_config = ConfigDict(extra='forbid')

    mode: str = Field(description='testnet | production | live')
    execution: Optional[ExecutionConfig] = Field()
    symbols_to_track: List[str] = Field(
        ...,
        description=(
            "List of symbols to track for multi-TF aggregation. "
            "Derived deterministically from strategies.yaml assignments by ConfigLoader unless explicitly set."
        ),
    )
    market_data: Optional[MarketDataConfig] = Field()

    # NOTE (TASK23.FIX.B): Forbidden SSOT mirrors are intentionally NOT part of TradingConfig.
    # - instruments SSOT: root.instruments (config/aurora/instruments.yaml)
    # - aurora per-symbol SSOT: strategies/aurora.yaml::aurora.assets (canonical: config.strategies.aurora.assets)
    # - domains SSOT: root.domains (config/aurora/domains.yaml)
    # - feature_engineering SSOT: domains.yaml (domain config), not trading.yaml

    # Legacy risk config (still used by DailyRiskState etc)
    risk: Dict[str, Any] = Field(
        description='Legacy risk configuration (daily gate, etc)')

    # TCA and Risk Budgets (Strictly Typed)
    tca_prefs: TCAPrefsConfig = Field(description='TCA Preferences')
    risk_budgets: RiskBudgetsConfig = Field(
        description='Risk Budgeting Configuration')

    # Risk management data sources (used for hybrid/live/testnet wiring)
    risk_management: "TradingRiskManagementConfig" = Field(...)

    # Ops configuration (killswitch, quiet hours)
    ops: Optional[OpsConfig] = Field(
        description='Operations config (panic killswitch, quiet hours, allowlist)')

    # CRITICAL: Domain-level mode configuration (Hybrid Mode)
    # Default is all-testnet for safety. Production MUST explicitly set live modes!
    domain_configuration: DomainConfigurationConfig = Field(
        description='Domain-level trading mode configuration for hybrid mode (live data + testnet execution)')

    # Backtest Configuration (Optional, used only when mode='backtest')
    backtest: Optional[BacktestConfig] = Field(
        default=None, description="Backtest specific settings")

    # Regime-specific TP/SL multipliers (for backtest overrides)
    regime_tpsl: Optional[Dict[str, Any]] = Field(
        default=None, description="Regime-specific TP/SL multipliers")

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

    api_key: Optional[str] = Field()
    api_secret: Optional[str] = Field()
    rest_url: Optional[str] = Field()
    # PURGE-DEAD-CONFIG-03: ws_url removed (hardcoded in market_data_connector.py, worker.py)


class BinanceApiConfig(BaseModel):
    """Binance API configuration (live + testnet)."""
    model_config = ConfigDict(extra='forbid')
    live: BinanceApiEnv = Field()
    testnet: BinanceApiEnv = Field()


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


class AccountObserverConfig(BaseModel):
    """Account observer configuration."""
    model_config = ConfigDict(extra='forbid')
    poll_interval: int = Field(description='Polling interval in seconds')


# ============================================================================
# OBSERVABILITY CONFIGURATION (CFG-OBS-001)
# ============================================================================
# Centralized logging, metrics, and tracing configuration.
# Replaces hardcoded values in main.py with YAML-driven config.
# ============================================================================


class LogRotationConfig(BaseModel):
    """Log file rotation settings."""
    model_config = ConfigDict(extra='forbid')

    max_bytes: int = Field(default=10485760, ge=1024,
                           description='Max bytes before rotation (default 10MB)')
    backup_count: int = Field(default=5, ge=1, le=100,
                              description='Number of backup files to keep')


class ConsoleLogConfig(BaseModel):
    """Console (stdout) logging configuration."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(default=True, description='Enable console logging')
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description='Console log level')
    format: Literal["text", "json"] = Field(
        default="text", description='Console log format')
    colorize: bool = Field(
        default=False, description='Enable ANSI color output (future)')


class CoreLogSinkConfig(BaseModel):
    """Core file sink configuration (aurora_core.log)."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(default=True, description='Enable core file logging')
    path: str = Field(default="logs/aurora_core.log",
                      description='Log file path')
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="DEBUG", description='File log level')
    format: Literal["text", "json"] = Field(
        default="text", description='File log format')
    max_bytes: Optional[int] = Field(
        default=None, description='Override rotation.max_bytes')
    backup_count: Optional[int] = Field(
        default=None, description='Override rotation.backup_count')


class DomainLogConfig(BaseModel):
    """Per-domain logging configuration."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True, description='Enable domain-specific log file')
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="DEBUG", description='Domain log level')
    max_bytes: int = Field(default=5242880, ge=1024,
                           description='Max bytes before rotation (default 5MB)')
    backup_count: int = Field(default=3, ge=1, le=100,
                              description='Number of backup files')


class EventChainLogConfig(BaseModel):
    """Structured event chain log configuration (JSON format)."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True, description='Enable event chain logging')
    path: str = Field(default="logs/event_chain.log",
                      description='Event chain log file path')
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description='Event chain log level')
    format: Literal["text", "json"] = Field(
        default="json", description='Event chain format (should be json)')
    max_bytes: int = Field(
        default=10485760, description='Max bytes before rotation')
    backup_count: int = Field(default=5, description='Number of backup files')


class ObservabilityLoggingConfig(BaseModel):
    """Complete logging configuration (SSOT for all log handlers)."""
    model_config = ConfigDict(extra='forbid')

    default_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description='Global default log level')
    default_format: Literal["text", "json"] = Field(
        default="text", description='Global default log format')
    rotation: LogRotationConfig = Field(
        default_factory=LogRotationConfig, description='Default rotation settings')
    console: ConsoleLogConfig = Field(
        default_factory=ConsoleLogConfig, description='Console sink config')
    core: CoreLogSinkConfig = Field(
        default_factory=CoreLogSinkConfig, description='Core file sink config')
    domains: Dict[str, DomainLogConfig] = Field(
        default_factory=dict, description='Per-domain log configs')
    event_chain: EventChainLogConfig = Field(
        default_factory=EventChainLogConfig, description='Event chain config')


class ObservabilityConfig(BaseModel):
    """Root observability configuration (logging, metrics, tracing)."""
    model_config = ConfigDict(extra='forbid')

    config_version: str = Field(
        default="1.0.0", description='Observability config version')
    logging: ObservabilityLoggingConfig = Field(
        default_factory=ObservabilityLoggingConfig, description='Logging configuration')
    # Future: metrics, tracing


# SCORCHED-EARTH-2026-01-27: LegacyLoggingConfig DELETED (zombie code, observability.yaml is SSOT)

class SystemMarketDataConfig(BaseModel):
    """System-level Market Data configuration."""
    model_config = ConfigDict(extra='forbid')

    queue_maxsize: int = Field(...,
                               description="Max size of IPC queue (worker → proxy)")
    # DEPRECATED: Not used in runtime (CFG-OBS-001)
    local_queue_maxsize: int = Field(
        default=10000, description="[DEPRECATED] Max size of local queue (proxy internal)")
    emit_workers: int = Field(
        default=4, description="[DEPRECATED] Thread pool size for non-blocking FSM.emit()")
    tick_ttl_ms: int = Field(
        ..., description="Max age of tick data in ms — older ticks are DROPPED")
    bar_ttl_ms: Optional[int] = Field(
        default=10000, description="Max age of bar data in ms (BAR-TTL-REFORM-01)")
    bar_event_age_mode: Literal["received", "close_ts"] = Field(
        default="received",
        description="How to calculate bar age: 'received' (arrival time) or 'close_ts' (event time)"
    )
    ws_heartbeat_sec: float = Field(
        ..., description="aiohttp WS heartbeat interval (sec) to keep connection alive")
    ws_receive_timeout_sec: float = Field(
        ..., description="Max time without WS messages (sec) before reconnect")
    proxy_batch_size: int = Field(...,
                                  description="Proxy consumer: max items processed per batch")
    proxy_queue_get_timeout_sec: float = Field(
        ..., description="Proxy consumer: blocking get() timeout (sec)")
    proxy_idle_sleep_sec: float = Field(
        ..., description="Proxy consumer: sleep when queue is empty (sec)")


class SystemConfig(BaseModel):
    """System configuration (framework-level)."""
    model_config = ConfigDict(extra='forbid')

    # SCORCHED-EARTH-2026-01-27: logging field DELETED (LegacyLoggingConfig zombie, observability.yaml is SSOT)
    market_data: Optional[SystemMarketDataConfig] = Field(
        default=None, description='Market data system settings')

    # Startup Guard Configuration (TASK-EXF-WIRE-STARTUP-09)
    validate_instruments_on_startup: bool = Field(
        default=True,
        description="Enable startup validation of instruments.yaml against exchange (fail-closed)"
    )
    warn_only_filters: bool = Field(
        default=False,
        description="If True, log warnings instead of crashing on filter mismatch (Dev/Shadow only)"
    )


class SystemRuntimeMeta(BaseModel):
    """Runtime metadata captured during config load."""

    model_config = ConfigDict(extra='forbid')

    config_name: Optional[str] = Field(
        default=None, description='Identifier of the loaded config profile')
    config_dir: Optional[str] = Field(
        default=None, description='Filesystem path of the config directory in use')


class SystemMetaConfig(BaseModel):
    """Service/runtime metadata preserved under a dedicated namespace."""

    model_config = ConfigDict(extra='forbid')

    system_config_version: Optional[str] = Field(default=None)
    regime_config_version: Optional[str] = Field(default=None)
    sequential_tests: Dict[str, Any] = Field()
    risk_core: Dict[str, Any] = Field()
    kelly: Dict[str, Any] = Field()
    calibrator: Dict[str, Any] = Field()
    hawkes: Dict[str, Any] = Field()
    # PURGE-DIRTY-DOZEN: Removed hotreload_whitelist (dead stub, hot-reload never implemented) - 2026-01-25
    hardening: Dict[str, Any] = Field()
    position_tracking: Dict[str, Any] = Field()
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
        description='Trading mode: testnet | production | live')
    trading: TradingConfig = Field()

    # Exchange/account/market configs
    binance_api: BinanceApiConfig = Field()
    account_observer: AccountObserverConfig = Field()

    # System configs
    system: SystemConfig = Field()
    system_meta: SystemMetaConfig = Field()
    ops: OpsConfig = Field()

    # Observability configs (CFG-OBS-001: Centralized logging/metrics/tracing)
    observability: ObservabilityConfig = Field(
        default_factory=ObservabilityConfig,
        description='Centralized observability config (logging, metrics, tracing)'
    )

    # NOTE: bridge config removed (BRIDGE-SUNSET-01)
    # AuroraBridge was removed; ExecPosFSM now handles TRADE_INTENT_PROPOSED directly.

    # Domain configs (New)
    domains: DomainsConfig = Field(
        description='Domain-specific configurations')

    # Canonical instruments SSOT (config/aurora/instruments.yaml)
    instruments: Dict[str, InstrumentPrecisionSpec] = Field(
        description='Canonical instrument precision map (symbol -> tick_size/step_size)')

    # Strategies registry SSOT (config/aurora/strategies.yaml)
    # CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION
    strategies_registry: Optional[StrategiesRegistryConfig] = Field(
        default=None, description='Strategy assignments + arbitration config (from strategies.yaml)')

    # Canonical strategy policy namespace (SSOT: strategies/<id>.yaml)
    strategies: StrategiesConfig = Field(
        description="Canonical strategies namespace (policy SSOT)")

    # App-specific overrides
    # TASK23.FIX.B: Legacy root aliases must NOT be required.
    # If provided explicitly, they act as overrides; otherwise they should not block startup.
    execution: Optional[ExecutionConfig] = Field(
        default=None, description='Override trading.execution if set')
    brackets: Optional[BracketsConfig] = Field(default=None)
    trailing: Optional[TrailingDefaultsConfig] = Field(
        default=None, description='Global trailing stop defaults')

    # Regime Detector Config (loaded from regime.yaml, Pydantic-validated)
    models: Optional[RegimeModelsConfig] = Field(
        default=None, description='Regime detection models from regime.yaml')

    # regime.yaml SSOT (top-level keys)
    # REG-FIX-01: BAR-ONLY SSOT - these fields are REQUIRED (no silent defaults)
    basis_tf_sec: int = Field(
        description='Bar-only regime updates: only process FEATURES_CALCULATED with matching tf_sec. '
                    'REQUIRED - missing value fails config load (fail-closed).'
    )
    uncertain_cutoff: float = Field(
        ge=0.0, le=1.0,
        description='Min confidence to emit non-UNCERTAIN regime. Below this threshold, demote to UNCERTAIN. '
                    'REQUIRED - missing value fails config load (fail-closed).'
    )
    # DM-CRITICAL-PATCHES-02: Liveness guard factor
    liveness_factor: int = Field(
        default=3, ge=1,
        description='If no regime heartbeat received within (basis_tf_sec * liveness_factor) seconds, '
                    'block trading. Default: 3 (i.e., 15 minutes for 5m basis).'
    )

    # HYSTERESIS-SLOPE-GATE-01: Regime stability
    hysteresis_bars: int = Field(
        default=3, ge=1, le=10,
        description='Number of consecutive bars to confirm regime change before switching stable_regime.'
    )

    # Volatility Slope Gate: block HIGH_VOL with dying momentum
    vol_slope_gate_enabled: bool = Field(
        default=True,
        description='Enable vol_ratio slope gate to detect "dying storm" (HIGH_VOL with falling momentum).'
    )
    vol_slope_gate_eps: float = Field(
        default=0.0, ge=-0.1, le=0.1,
        description='Slope threshold: if vol_ratio slope <= eps for confirm_bars, force UNCERTAIN.'
    )
    vol_slope_gate_confirm_bars: int = Field(
        default=2, ge=1, le=5,
        description='Number of bars slope must stay below eps to trigger gate.'
    )

    # SCORCHED-EARTH-2026-01-27: hmm and features fields DELETED (zero runtime references, regime.yaml not read by code)
    # PURGE-DIRTY-DOZEN: Removed hotreload_whitelist (dead stub, hot-reload never implemented) - 2026-01-25

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
    def _forbid_legacy_normalize_signals_in_live(self) -> "AuroraConfig":
        """Fail-fast: legacy normalize mode must not run in live/production/hybrid."""
        mode = str(getattr(self, "trading_mode", "")).lower()
        is_live_like = mode in ("live", "production",
                                "hybrid_live_data_testnet_exec")

        aurora_cfg = getattr(self.strategies, "aurora", None)
        if aurora_cfg is None:
            return self
        decision = getattr(aurora_cfg, "decision", None)
        if decision is None:
            return self
        signals = getattr(decision, "signals", None)
        if signals is None:
            return self

        if is_live_like and str(signals.normalize_signals_mode) == "legacy_v1":
            raise ValueError(
                "strategies.aurora.decision.signals.normalize_signals_mode='legacy_v1' is forbidden in live/production"
            )
        return self

    @model_validator(mode="after")
    def _fail_closed_validate_aurora_tpsl_ssot(self) -> "AuroraConfig":
        """
        Fail-closed: TP/SL parameters must come from YAML SSOT (strategies/aurora.yaml per-asset config).

        This prevents silent runtime fallbacks that can quantize DOGE to 0.10000/0.20000 when tick_size is wrong
        or when per-asset exit/take_profit config is missing.
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
        if aurora is None:
            raise ValueError(
                "strategies.aurora is required: TP/SL SSOT lives in config/aurora/strategies/aurora.yaml"
            )

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

        if missing:
            raise ValueError("TP/SL SSOT validation failed: " +
                             "; ".join(sorted(missing)))

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
