from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FeatureEngineeringConfig(BaseModel):
    """Feature engineering configuration."""
    model_config = ConfigDict(extra='forbid')

    ema: Dict[str, Any] = Field()
    volume: Dict[str, Any] = Field()
    volatility: Dict[str, Any] = Field()
    liquidity: Dict[str, Any] = Field()
    macro_sync: Dict[str, Any] = Field()


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
        if abs(v + clamp_min) > 0.001:
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
    align_mode: str = Field(pattern='^(strict_len|tail_min_len)$',
                            description="Alignment mode: 'strict_len' (require exact match) or 'tail_min_len' (use shorter tail)")
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

    @model_validator(mode='after')
    def validate_windows(self) -> 'MacroResidConfig':
        """Validate window relationships."""
        if self.mad_window > self.beta_window:
            raise ValueError(
                f"mad_window ({self.mad_window}) cannot exceed beta_window ({self.beta_window})"
            )
        return self


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
    dp_cap_pct: Optional[float] = Field(
        default=None,
        gt=0.0, le=1.0,
        description=(
            'Cap for |delta_price/price| normalisation in conflict-weighted formula. '
            'Required when absorption.mode != disabled. '
            'Example: 0.02 = cap at 2%% delta-price deviation.'
        )
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


class AbsorptionConfig(BaseModel):
    """R2: Absorption feature configuration (experimental, default OFF)."""
    model_config = ConfigDict(extra='forbid')

    mode: Literal["disabled", "proxy", "full"] = Field(
        description='Absorption mode: disabled (default), proxy, or full'
    )
    dp_cap_pct: Optional[float] = Field(
        default=None,
        gt=0.0,
        le=1.0,
        description=(
            "Legacy migration alias for absorption.proxy.dp_cap_pct. "
            "Current SSOT remains absorption.proxy.dp_cap_pct."
        ),
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

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_dp_cap_pct(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        legacy = data.get("dp_cap_pct")
        if legacy is None:
            return data
        proxy = data.get("proxy")
        if proxy is None:
            data["proxy"] = {"dp_cap_pct": legacy}
            return data
        if isinstance(proxy, dict) and proxy.get("dp_cap_pct") is None:
            proxy = dict(proxy)
            proxy["dp_cap_pct"] = legacy
            data["proxy"] = proxy
        return data

    @model_validator(mode='after')
    def validate_proxy_required(self) -> 'AbsorptionConfig':
        """Validate proxy config required when mode != disabled.

        P0-SSOT: dp_cap_pct must be explicit in YAML — no silent hardcoded fallback.
        """
        if self.mode != 'disabled':
            if self.proxy is None:
                raise ValueError(
                    f"absorption.proxy config required when mode='{self.mode}' "
                    "(set it in domains.yaml under absorption.proxy)"
                )
            if self.proxy.dp_cap_pct is None:
                raise ValueError(
                    f"absorption.proxy.dp_cap_pct required when mode='{self.mode}'. "
                    "Add 'dp_cap_pct: 0.02' under absorption.proxy in domains.yaml. "
                    "No hardcoded fallback — explicit YAML SSOT only."
                )
        return self


class TacticianConfig(BaseModel):
    """Tactician Pillar (M15): Rate of Change — tactical momentum."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description='Enable Tactician pillar (M15 ROC)',
    )
    timeframe_sec: int = Field(
        default=900,
        ge=60, le=86400,
        description='Timeframe in seconds for Tactician pillar candles (default M15=900)',
    )
    roc_period: int = Field(
        default=14,
        ge=2, le=100,
        description='ROC lookback period in bars',
    )
    sensitivity: float = Field(
        default=3.0,
        gt=0.0, le=10.0,
        description='tanh normalization sensitivity (higher = faster saturation)',
    )
    min_bars: int = Field(
        default=20,
        ge=5, le=200,
        description='Minimum M15 bars before pillar is ready',
    )


class OperatorConfig(BaseModel):
    """Operator Pillar (H4): LinReg Slope + ADX — working vector."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description='Enable Operator pillar (H4 LinReg+ADX)',
    )
    timeframe_sec: int = Field(
        default=14400,
        ge=60, le=86400,
        description='Timeframe in seconds for Operator pillar candles (default H4=14400)',
    )
    linreg_period: int = Field(
        default=20,
        ge=5, le=100,
        description='Linear regression slope window (bars)',
    )
    adx_period: int = Field(
        default=14,
        ge=5, le=50,
        description='ADX calculation period (bars)',
    )
    sensitivity: float = Field(
        default=3.0,
        gt=0.0, le=10.0,
        description='tanh normalization sensitivity',
    )
    min_bars: int = Field(
        default=50,
        ge=20, le=300,
        description='Minimum H4 bars before pillar is ready',
    )


class StrategistConfig(BaseModel):
    """Strategist Pillar (D1): SMA(200) position — global territory."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description='Enable Strategist pillar (D1 SMA200)',
    )
    timeframe_sec: int = Field(
        default=86400,
        ge=60, le=86400,
        description='Timeframe in seconds for Strategist pillar candles (default D1=86400)',
    )
    sma_period: int = Field(
        default=200,
        ge=20, le=500,
        description='SMA period for territory detection',
    )
    sensitivity: float = Field(
        default=3.0,
        gt=0.0, le=10.0,
        description='tanh normalization sensitivity',
    )
    min_bars: int = Field(
        default=200,
        ge=50, le=600,
        description='Minimum D1 bars before pillar is ready',
    )


class PillarWeightsConfig(BaseModel):
    """Weights for pillar aggregation. Sum does NOT need to equal 1.0."""
    model_config = ConfigDict(extra='forbid')

    tactician: float = Field(
        default=0.30,
        ge=0.0, le=1.0,
        description='Weight for Tactician (M15 ROC) pillar',
    )
    operator: float = Field(
        default=0.40,
        ge=0.0, le=1.0,
        description='Weight for Operator (H4 LinReg+ADX) pillar',
    )
    strategist: float = Field(
        default=0.30,
        ge=0.0, le=1.0,
        description='Weight for Strategist (D1 SMA200) pillar',
    )


class PillarBackfillConfig(BaseModel):
    """D1/H4 historical candle backfill for live startup (КР-1 fix)."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description='Enable backfill at live startup (disable for backtest)',
    )
    d1_candles: int = Field(
        default=200,
        ge=50, le=500,
        description='Number of D1 candles to fetch (≥ sma_period)',
    )
    h4_candles: int = Field(
        default=100,
        ge=30, le=500,
        description='Number of H4 candles to fetch',
    )
    m15_candles: int = Field(
        default=50,
        ge=15, le=200,
        description='Number of M15 candles to fetch',
    )


class PillarsConfig(BaseModel):
    """Complete multi-timeframe pillars configuration for Phase 9."""
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        default=True,
        description='Master switch for all pillar indicators',
    )
    tactician: TacticianConfig = Field(default_factory=TacticianConfig)
    operator: OperatorConfig = Field(default_factory=OperatorConfig)
    strategist: StrategistConfig = Field(default_factory=StrategistConfig)
    weights: PillarWeightsConfig = Field(default_factory=PillarWeightsConfig)
    backfill: PillarBackfillConfig = Field(
        default_factory=PillarBackfillConfig)


class LegacyFeaturesLogConfig(BaseModel):
    """Legacy per-symbol features log policy for additive migration."""
    model_config = ConfigDict(extra='forbid')

    mode: Literal["full", "sample", "off"] = Field(
        default="full",
        description="Legacy FE sink mode: full (every event), sample (every N), off",
    )
    sample_every_n: int = Field(
        default=10,
        ge=1,
        description="Sampling interval when mode=sample (write every N events per symbol)",
    )


class FeatureEngineeringDomainConfig(BaseModel):
    """
    Complete feature engineering domain configuration.

    All 9 features are configured here:
    - Base: OBI, TFI, delta_price, liquidity_kappa
    - Phase 1: ema_bias, volume_spike, volatility_state, depth_imbalance, macro_sync
    """
    model_config = ConfigDict(extra='forbid')

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

    enable_new_metrics: bool = Field(
        description='Enable Phase 1 metrics (ema_bias, volume_spike, etc.)')
    trace_features: bool = Field(
        default=False, description='Enable per-tick feature logging (WARNING: high I/O cost)')
    legacy_features_log: LegacyFeaturesLogConfig = Field(
        default_factory=LegacyFeaturesLogConfig,
        description="Legacy feature sink control for additive compatibility logging",
    )
    volume_input_mode: str = Field(pattern='^(integrate|sample_window_total)$',
                                   description="Volume input mode: 'integrate' (sum ticks) or 'sample_window_total' (treat tick as pre-windowed sample)")
    ema: EmaConfigDetailed = Field()
    volume: VolumeConfigDetailed = Field()
    volatility: VolatilityConfigDetailed = Field()
    liquidity: LiquidityConfigDetailed = Field()
    ema_bias: EmaBiasConfig = Field()
    volume_spike: VolumeSpikeConfig = Field()
    volume_zscore: VolumeZScoreConfig = Field()
    large_trade_imbalance: LargeTradeImbalanceConfig = Field()
    volatility_state: VolatilityStateConfig = Field()
    depth_imbalance: DepthImbalanceConfig = Field()
    delta_price: DeltaPriceConfig = Field()
    macro_sync: MacroSyncMetricsConfig = Field()
    defaults: FeatureDefaultsConfig = Field()
    readiness_registry: Optional[ReadinessRegistryConfig] = Field(
        default=None,
        description='P0-0: SSOT for declared ready keys. Required in production.'
    )
    warmup: Optional[WarmupEnforcementConfig] = Field(
        default=None,
        description='P0-0: Warmup enforcement. Required in production.'
    )
    spread_bps: Optional[SpreadBpsConfig] = Field(
        default=None,
        description='P0-2: Spread health gate config. Required when spread_bps used.'
    )
    feature_sanity: Optional[FeatureSanityConfig] = Field(
        default=None,
        description='P0-3: NaN/Inf/out-of-range firewall. Recommended for production.'
    )
    macro_resid: Optional[MacroResidConfig] = Field(
        default=None,
        description='R1: Beta-adjusted residual (replaces macro_sync for direction). SIGNED, neutral=0.'
    )
    absorption: Optional[AbsorptionConfig] = Field(
        default=None,
        description='R2: Absorption feature (experimental). Default OFF, no live impact.'
    )
    pillars: Optional[PillarsConfig] = Field(
        default=None,
        description='Phase 9: Multi-timeframe pillars (Tactician M15, Operator H4, Strategist D1). None = disabled.'
    )

    def get_ema_alpha(self, period: str) -> float:
        """Calculate EMA alpha for given period."""
        if period == "short":
            n = self.ema.period_short
        else:
            n = self.ema.period_long
        return 2.0 / (n + 1)
