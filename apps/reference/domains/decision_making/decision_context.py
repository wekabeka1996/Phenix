"""
Decision Context - Typed Feature Views for Decision Making.

FTR-06: Implements strongly-typed Views for semantic feature grouping.

This module provides:
- TrendView: EMA bias, delta price, bullish/bearish signals
- FlowView: Order flow, trade flow imbalance
- VolatilityView: Volatility state, volume spike
- LiquidityView: Liquidity kappa, spread
- CrowdingView: Futures crowding (funding rate, OI delta)
- DecisionContext: Main container with lazy-parsed Views

Architecture:
- All fields are Decimal for financial precision
- V2 features are Optional (graceful fallback to defaults)
- Views expose computed properties (is_bullish, is_crowded_long, etc.)

Reference: FTR_FEATURES_FUTURES_V2_DESIGN.md Section 6 (doc removed in LEGACY-PURGE-WAVE-1)
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """
    Safely convert any value to Decimal.
    
    Args:
        value: Value to convert (str, float, int, Decimal, None)
        default: Default value if conversion fails
        
    Returns:
        Decimal value or default
    """
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def safe_decimal_optional(value: Any) -> Optional[Decimal]:
    """
    Safely convert value to Decimal, returning None if missing/invalid.
    
    For V2 optional features that may not exist in payload.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


# =============================================================================
# FEATURE VIEWS
# =============================================================================

@dataclass(frozen=True)
class TrendView:
    """
    Trend-related features view.
    
    Fields:
        ema_bias: EMA bias [0, 1] - 0.5 neutral, >0.5 bullish, <0.5 bearish
        delta_price: Price change from previous tick
        
    Properties:
        is_bullish: True if ema_bias > 0.5
        is_bearish: True if ema_bias < 0.5
        is_neutral: True if ema_bias ~= 0.5
    """
    ema_bias: Decimal = Decimal("0.5")
    delta_price: Decimal = Decimal("0")
    
    @property
    def is_bullish(self) -> bool:
        """True if EMA bias indicates bullish trend."""
        return self.ema_bias > Decimal("0.5")
    
    @property
    def is_bearish(self) -> bool:
        """True if EMA bias indicates bearish trend."""
        return self.ema_bias < Decimal("0.5")
    
    @property
    def is_neutral(self) -> bool:
        """True if EMA bias is approximately neutral (0.45 - 0.55)."""
        return Decimal("0.45") <= self.ema_bias <= Decimal("0.55")
    
    @property
    def trend_strength(self) -> Decimal:
        """Absolute distance from neutral (0 to 0.5)."""
        return abs(self.ema_bias - Decimal("0.5"))


@dataclass(frozen=True)
class FlowView:
    """
    Order/Trade flow features view.
    
    Fields:
        obi: Order Book Imbalance [-1, 1]
        tfi: Trade Flow Imbalance [-1, 1]
        large_trade_imbalance: V2 - Large trade imbalance [0, 1] (Optional)
        
    Properties:
        combined_pressure: Average of available flow metrics, normalized to [-1, 1]
    """
    obi: Decimal = Decimal("0")
    tfi: Decimal = Decimal("0")
    large_trade_imbalance: Optional[Decimal] = None
    
    @property
    def combined_pressure(self) -> Decimal:
        """
        Combined flow pressure from all available metrics.
        
        OBI and TFI are [-1, 1], large_trade_imbalance is [0, 1] (needs normalization).
        Returns average of available metrics in [-1, 1] range.
        """
        values = [self.obi, self.tfi]
        
        # Normalize large_trade_imbalance from [0, 1] to [-1, 1]
        if self.large_trade_imbalance is not None:
            normalized_lti = (self.large_trade_imbalance - Decimal("0.5")) * 2
            values.append(normalized_lti)
        
        if not values:
            return Decimal("0")
        
        return sum(values) / len(values)
    
    @property
    def is_buy_pressure(self) -> bool:
        """True if combined flow indicates buying pressure."""
        return self.combined_pressure > Decimal("0.2")
    
    @property
    def is_sell_pressure(self) -> bool:
        """True if combined flow indicates selling pressure."""
        return self.combined_pressure < Decimal("-0.2")


@dataclass(frozen=True)
class VolatilityView:
    """
    Volatility and volume features view.
    
    Fields:
        volatility_state: Volatility state [0, 1]
        volume_spike: Volume spike ratio [0, 1]
        volume_zscore: V2 - Volume Z-score normalized [0, 1] (Optional)
        
    Properties:
        is_high_volatility: True if volatility_state > 0.7
        is_volume_spike: True if volume_spike > 0.7
    """
    volatility_state: Decimal = Decimal("0.5")
    volume_spike: Decimal = Decimal("0.5")
    volume_zscore: Optional[Decimal] = None
    
    @property
    def is_high_volatility(self) -> bool:
        """True if volatility is elevated (> 0.7)."""
        return self.volatility_state > Decimal("0.7")
    
    @property
    def is_low_volatility(self) -> bool:
        """True if volatility is low (< 0.3)."""
        return self.volatility_state < Decimal("0.3")
    
    @property
    def is_volume_spike(self) -> bool:
        """True if volume spike is significant (> 0.7)."""
        return self.volume_spike > Decimal("0.7")
    
    @property
    def combined_intensity(self) -> Decimal:
        """Combined volatility and volume intensity."""
        values = [self.volatility_state, self.volume_spike]
        if self.volume_zscore is not None:
            values.append(self.volume_zscore)
        return sum(values) / len(values)


@dataclass(frozen=True)
class LiquidityView:
    """
    Liquidity features view.
    
    Fields:
        liquidity_kappa: Liquidity measure [kappa_min, kappa_max]
        depth_imbalance: Depth imbalance [0, 1]
        spread_bps: V2 - Spread in basis points (Optional)
        
    Properties:
        is_illiquid: True if kappa < 0.5 or spread > 50bps
    """
    liquidity_kappa: Decimal = Decimal("0.5")
    depth_imbalance: Decimal = Decimal("0.5")
    spread_bps: Optional[Decimal] = None
    
    @property
    def is_illiquid(self) -> bool:
        """True if liquidity is poor."""
        if self.liquidity_kappa < Decimal("0.5"):
            return True
        if self.spread_bps is not None and self.spread_bps > Decimal("50"):
            return True
        return False
    
    @property
    def is_liquid(self) -> bool:
        """True if liquidity is good."""
        return self.liquidity_kappa > Decimal("0.7")
    
    @property
    def effective_spread(self) -> Decimal:
        """Spread in bps, defaulting to estimate from kappa if missing."""
        if self.spread_bps is not None:
            return self.spread_bps
        # Rough estimate: illiquid (kappa=0.3) ~ 100bps, liquid (kappa=1.0) ~ 5bps
        return (Decimal("1") - self.liquidity_kappa) * Decimal("150")


@dataclass(frozen=True)
class CrowdingView:
    """
    Futures crowding features view (FTR-05).
    
    Fields:
        funding_rate_normalized: Funding rate normalized [-1, 1] (Optional)
        oi_delta_pct: Open Interest delta percentage (Optional)
        funding_rate: Raw funding rate (Optional)
        
    Properties:
        is_crowded_long: True if funding > 0.5 (longs pay shorts heavily)
        is_crowded_short: True if funding < -0.5 (shorts pay longs heavily)
    """
    funding_rate_normalized: Optional[Decimal] = None
    oi_delta_pct: Optional[Decimal] = None
    funding_rate: Optional[Decimal] = None
    
    @property
    def is_crowded_long(self) -> bool:
        """True if market is crowded long (extreme positive funding)."""
        if self.funding_rate_normalized is None:
            return False
        return self.funding_rate_normalized > Decimal("0.5")
    
    @property
    def is_crowded_short(self) -> bool:
        """True if market is crowded short (extreme negative funding)."""
        if self.funding_rate_normalized is None:
            return False
        return self.funding_rate_normalized < Decimal("-0.5")
    
    @property
    def has_data(self) -> bool:
        """True if any crowding data is available."""
        return self.funding_rate_normalized is not None or self.oi_delta_pct is not None
    
    @property
    def is_oi_increasing(self) -> bool:
        """True if Open Interest is increasing (> 1%)."""
        if self.oi_delta_pct is None:
            return False
        return self.oi_delta_pct > Decimal("1")
    
    @property
    def is_oi_decreasing(self) -> bool:
        """True if Open Interest is decreasing (< -1%)."""
        if self.oi_delta_pct is None:
            return False
        return self.oi_delta_pct < Decimal("-1")


# =============================================================================
# DECISION CONTEXT
# =============================================================================

@dataclass
class DecisionContext:
    """
    Main container for feature-based decision making.
    
    Provides typed Views for semantic access to features.
    Lazy-parses raw features dict into strongly-typed Views.
    
    Usage:
        ctx = DecisionContext(
            symbol="BTCUSDT",
            ts=1234567890000,
            features=payload["features"]
        )
        
        if ctx.trend.is_bullish and not ctx.crowding.is_crowded_long:
            # Trade logic
    
    FTR-06: Typed context for decision_making domain.
    """
    symbol: str
    ts: int
    features: Dict[str, str] = field(default_factory=dict)

    # Tracks missing/invalid raw feature keys observed while parsing.
    # Values are short reasons like: "missing", "invalid", "invalid_optional".
    missing_fields: Dict[str, str] = field(default_factory=dict)
    
    # Cached views (populated lazily)
    _trend: Optional[TrendView] = field(default=None, repr=False)
    _flow: Optional[FlowView] = field(default=None, repr=False)
    _volatility: Optional[VolatilityView] = field(default=None, repr=False)
    _liquidity: Optional[LiquidityView] = field(default=None, repr=False)
    _crowding: Optional[CrowdingView] = field(default=None, repr=False)
    
    def _get_feature(self, key: str, default: Decimal = Decimal("0")) -> Decimal:
        """Get feature value as Decimal with default (and track missing/invalid)."""
        if key not in self.features:
            self.missing_fields.setdefault(key, "missing")
            return default

        raw_value = self.features.get(key)
        if raw_value is None:
            self.missing_fields.setdefault(key, "missing")
            return default
        try:
            return Decimal(str(raw_value))
        except (InvalidOperation, ValueError, TypeError):
            self.missing_fields.setdefault(key, "invalid")
            return default
    
    def _get_feature_optional(self, key: str) -> Optional[Decimal]:
        """Get optional feature value as Decimal, None if missing (track invalid if present)."""
        if key not in self.features:
            return None
        value = self.features.get(key)
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            self.missing_fields.setdefault(key, "invalid_optional")
            return None
    
    @property
    def trend(self) -> TrendView:
        """
        Get TrendView with EMA bias and delta price.
        
        Parsed from features: ema_bias, delta_price
        """
        if self._trend is None:
            self._trend = TrendView(
                ema_bias=self._get_feature("ema_bias", Decimal("0.5")),
                delta_price=self._get_feature("delta_price", Decimal("0")),
            )
        return self._trend
    
    @property
    def flow(self) -> FlowView:
        """
        Get FlowView with order/trade flow metrics.
        
        Parsed from features: obi, tfi, large_trade_imbalance (v2)
        """
        if self._flow is None:
            self._flow = FlowView(
                obi=self._get_feature("obi", Decimal("0")),
                tfi=self._get_feature("tfi", Decimal("0")),
                large_trade_imbalance=self._get_feature_optional("large_trade_imbalance"),
            )
        return self._flow
    
    @property
    def volatility(self) -> VolatilityView:
        """
        Get VolatilityView with volatility and volume metrics.
        
        Parsed from features: volatility_state, volume_spike, volume_zscore (v2)
        """
        if self._volatility is None:
            self._volatility = VolatilityView(
                volatility_state=self._get_feature("volatility_state", Decimal("0.5")),
                volume_spike=self._get_feature("volume_spike", Decimal("0.5")),
                volume_zscore=self._get_feature_optional("volume_zscore"),
            )
        return self._volatility
    
    @property
    def liquidity(self) -> LiquidityView:
        """
        Get LiquidityView with liquidity metrics.
        
        Parsed from features: liquidity_kappa, depth_imbalance, spread_bps (v2)
        """
        if self._liquidity is None:
            self._liquidity = LiquidityView(
                liquidity_kappa=self._get_feature("liquidity_kappa", Decimal("0.5")),
                depth_imbalance=self._get_feature("depth_imbalance", Decimal("0.5")),
                spread_bps=self._get_feature_optional("spread_bps"),
            )
        return self._liquidity
    
    @property
    def crowding(self) -> CrowdingView:
        """
        Get CrowdingView with futures crowding metrics.
        
        Parsed from features: funding_rate_normalized, oi_delta_pct, funding_rate (v2)
        """
        if self._crowding is None:
            self._crowding = CrowdingView(
                funding_rate_normalized=self._get_feature_optional("funding_rate_normalized"),
                oi_delta_pct=self._get_feature_optional("oi_delta_pct"),
                funding_rate=self._get_feature_optional("funding_rate"),
            )
        return self._crowding
    
    @property
    def price(self) -> Decimal:
        """Get current price from features."""
        return self._get_feature("price", Decimal("0"))
    
    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================
    
    def is_favorable_for_long(self) -> bool:
        """
        Quick check if conditions favor a long position.
        
        Checks: bullish trend + buy pressure + not crowded long
        """
        return (
            self.trend.is_bullish and 
            self.flow.is_buy_pressure and 
            not self.crowding.is_crowded_long
        )
    
    def is_favorable_for_short(self) -> bool:
        """
        Quick check if conditions favor a short position.
        
        Checks: bearish trend + sell pressure + not crowded short
        """
        return (
            self.trend.is_bearish and 
            self.flow.is_sell_pressure and 
            not self.crowding.is_crowded_short
        )
    
    def should_reduce_risk(self) -> bool:
        """
        Quick check if conditions warrant risk reduction.
        
        Checks: high volatility OR illiquid market
        """
        return self.volatility.is_high_volatility or self.liquidity.is_illiquid
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dict for logging/debugging."""
        return {
            "symbol": self.symbol,
            "ts": self.ts,
            "trend": {
                "ema_bias": str(self.trend.ema_bias),
                "is_bullish": self.trend.is_bullish,
                "is_bearish": self.trend.is_bearish,
            },
            "flow": {
                "obi": str(self.flow.obi),
                "tfi": str(self.flow.tfi),
                "combined_pressure": str(self.flow.combined_pressure),
            },
            "volatility": {
                "volatility_state": str(self.volatility.volatility_state),
                "is_high": self.volatility.is_high_volatility,
            },
            "liquidity": {
                "kappa": str(self.liquidity.liquidity_kappa),
                "is_illiquid": self.liquidity.is_illiquid,
            },
            "crowding": {
                "funding_normalized": str(self.crowding.funding_rate_normalized) if self.crowding.funding_rate_normalized else None,
                "is_crowded_long": self.crowding.is_crowded_long,
                "is_crowded_short": self.crowding.is_crowded_short,
            },
        }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_decision_context(
    symbol: str,
    ts: int,
    features: Dict[str, str],
) -> DecisionContext:
    """
    Factory function to create DecisionContext from event payload.
    
    Args:
        symbol: Trading symbol
        ts: Timestamp in ms
        features: Raw features dict from EVT:FEATURES_CALCULATED
        
    Returns:
        DecisionContext with lazy-parsed Views
    """
    return DecisionContext(
        symbol=symbol,
        ts=ts,
        features=features or {},
    )
