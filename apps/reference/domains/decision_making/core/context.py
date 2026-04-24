"""Typed, lazy-parsed feature views used by decision-making code.

DecisionContext wraps a raw features mapping and exposes semantic view objects
for trend, flow, volatility, liquidity, and crowding. Parsing is lazy: the
module records missing or invalid raw keys only when a corresponding property
is accessed.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional, Any


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Convert a raw value to Decimal without raising.

    This helper is standalone: unlike DecisionContext._get_feature(), it does
    not record diagnostics about missing or invalid inputs.
    """
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def safe_decimal_optional(value: Any) -> Optional[Decimal]:
    """Convert a raw value to Decimal or return None on missing/invalid input."""
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
    """Immutable view over trend-oriented features.

    The bullish/bearish helpers assume ema_bias follows the caller's normalized
    convention where 0.5 is neutral; this class does not clamp or validate it.
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
    """Immutable view over order-flow and trade-flow features.

    OBI and TFI are used as provided. large_trade_imbalance, when present, is
    only re-centered around 0.5 before being averaged with the other signals.
    """
    obi: Decimal = Decimal("0")
    tfi: Decimal = Decimal("0")
    large_trade_imbalance: Optional[Decimal] = None

    @property
    def combined_pressure(self) -> Decimal:
        """Return the arithmetic mean of the available flow signals.

        large_trade_imbalance is translated from a 0.5-centered convention into
        the same signed frame as OBI/TFI. No final clamping is applied here.
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
    """Immutable view over volatility and volume-intensity signals.

    Threshold helpers use fixed local cutoffs; the raw values are not validated
    or normalized inside this class.
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
        """Average the present volatility and volume-intensity signals."""
        values = [self.volatility_state, self.volume_spike]
        if self.volume_zscore is not None:
            values.append(self.volume_zscore)
        return sum(values) / len(values)


@dataclass(frozen=True)
class LiquidityView:
    """Immutable view over liquidity-oriented features.

    The boolean helpers apply simple local heuristics over liquidity_kappa and
    optional spread_bps; no external instrument metadata is consulted here.
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
        """Return spread_bps or a simple inverse-kappa heuristic when absent."""
        if self.spread_bps is not None:
            return self.spread_bps
        # Heuristic only: lower kappa maps linearly to a larger implied spread.
        return (Decimal("1") - self.liquidity_kappa) * Decimal("150")


@dataclass(frozen=True)
class CrowdingView:
    """Immutable view over optional futures crowding signals.

    Missing crowding inputs behave as no-data, not as an explicit neutral
    market statement.
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
    """Lazy parser that exposes typed semantic views over a raw feature map.

    Accessing a property can mutate missing_fields because diagnostics are
    collected on demand rather than during __init__.
    """
    symbol: str
    ts: int
    features: Dict[str, Any] = field(default_factory=dict)

    # Diagnostics are populated lazily as individual features or views are read.
    missing_fields: Dict[str, str] = field(default_factory=dict)

    # Cached views (populated lazily)
    _trend: Optional[TrendView] = field(default=None, repr=False)
    _flow: Optional[FlowView] = field(default=None, repr=False)
    _volatility: Optional[VolatilityView] = field(default=None, repr=False)
    _liquidity: Optional[LiquidityView] = field(default=None, repr=False)
    _crowding: Optional[CrowdingView] = field(default=None, repr=False)

    def _get_feature(self, key: str, default: Decimal = Decimal("0")) -> Decimal:
        """Return a required feature as Decimal and record missing/invalid input."""
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
        """Return an optional feature as Decimal, tracking only invalid payloads."""
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
        """Parse and cache the trend-oriented feature view."""
        if self._trend is None:
            self._trend = TrendView(
                ema_bias=self._get_feature("ema_bias", Decimal("0.5")),
                delta_price=self._get_feature("delta_price", Decimal("0")),
            )
        return self._trend

    @property
    def flow(self) -> FlowView:
        """Parse and cache the order-flow/trade-flow view."""
        if self._flow is None:
            self._flow = FlowView(
                obi=self._get_feature("obi", Decimal("0")),
                tfi=self._get_feature("tfi", Decimal("0")),
                large_trade_imbalance=self._get_feature_optional(
                    "large_trade_imbalance"),
            )
        return self._flow

    @property
    def volatility(self) -> VolatilityView:
        """Parse and cache the volatility-and-volume view."""
        if self._volatility is None:
            self._volatility = VolatilityView(
                volatility_state=self._get_feature(
                    "volatility_state", Decimal("0.5")),
                volume_spike=self._get_feature("volume_spike", Decimal("0.5")),
                volume_zscore=self._get_feature_optional("volume_zscore"),
            )
        return self._volatility

    @property
    def liquidity(self) -> LiquidityView:
        """Parse and cache the liquidity-oriented view."""
        if self._liquidity is None:
            self._liquidity = LiquidityView(
                liquidity_kappa=self._get_feature(
                    "liquidity_kappa", Decimal("0.5")),
                depth_imbalance=self._get_feature(
                    "depth_imbalance", Decimal("0.5")),
                spread_bps=self._get_feature_optional("spread_bps"),
            )
        return self._liquidity

    @property
    def crowding(self) -> CrowdingView:
        """Parse and cache the futures-crowding view."""
        if self._crowding is None:
            self._crowding = CrowdingView(
                funding_rate_normalized=self._get_feature_optional(
                    "funding_rate_normalized"),
                oi_delta_pct=self._get_feature_optional("oi_delta_pct"),
                funding_rate=self._get_feature_optional("funding_rate"),
            )
        return self._crowding

    @property
    def price(self) -> Decimal:
        """Return the current price feature, defaulting to Decimal("0") on failure."""
        return self._get_feature("price", Decimal("0"))

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    def is_favorable_for_long(self) -> bool:
        """Return True when the local convenience heuristics favor a long."""
        return (
            self.trend.is_bullish and
            self.flow.is_buy_pressure and
            not self.crowding.is_crowded_long
        )

    def is_favorable_for_short(self) -> bool:
        """Return True when the local convenience heuristics favor a short."""
        return (
            self.trend.is_bearish and
            self.flow.is_sell_pressure and
            not self.crowding.is_crowded_short
        )

    def should_reduce_risk(self) -> bool:
        """Return True when the local heuristics indicate elevated execution risk."""
        return self.volatility.is_high_volatility or self.liquidity.is_illiquid

    def to_dict(self) -> Dict[str, Any]:
        """Build a debug-friendly snapshot of the currently exposed context."""
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
                # Zero funding is valid data and must not be collapsed to None.
                "funding_normalized": str(self.crowding.funding_rate_normalized) if self.crowding.funding_rate_normalized is not None else None,
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
    features: Dict[str, Any],
) -> DecisionContext:
    """Create a DecisionContext from an event payload feature mapping."""
    return DecisionContext(
        symbol=symbol,
        ts=ts,
        features=features or {},
    )
