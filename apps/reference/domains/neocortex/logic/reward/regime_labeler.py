"""
RegimeLabeler: Compute realized market regime from feature snapshots.

REGIME_PIVOT_PLAN Section 3.2 — Ground Truth Labels.

Given features at time t and features at time t+H, determines what regime
ACTUALLY materialized. This is the self-supervised label for PPO training.

Regime indices (action space mapping):
    0: TREND_UP
    1: TREND_DOWN
    2: MEAN_REVERSION
    3: HIGH_VOLATILITY
    4: EXHAUSTION

Feature normalization notes (logs/features/*.log):
    - delta_price: raw USD change (varies wildly by symbol)
      → normalized internally as delta_price / price (percentage change)
    - ema_bias: [0, 1] centered at 0.5 (0.5 = neutral)
      → centered internally as ema_bias - 0.5
    - volatility_state: [0, 1] where 0=calm, 1=high vol
      (replaces volatility_atr_pct which is not present in feature logs)
    - volatility_atr_pct / volatility_range_pct: NOT PRESENT in feature logs
"""

from __future__ import annotations

# QUARANTINED: legacy_runtime
__quarantined__ = True

import logging
import math
from numbers import Real
from typing import Mapping

logger = logging.getLogger(__name__)

# Action-space constants (must match PPO action_dim=5)
TREND_UP = 0
TREND_DOWN = 1
MEAN_REVERSION = 2
HIGH_VOLATILITY = 3
EXHAUSTION = 4

REGIME_NAMES = {
    TREND_UP: "PREDICT_TREND_UP",
    TREND_DOWN: "PREDICT_TREND_DOWN",
    MEAN_REVERSION: "PREDICT_MEAN_REVERSION",
    HIGH_VOLATILITY: "PREDICT_HIGH_VOLATILITY",
    EXHAUSTION: "PREDICT_EXHAUSTION",
}

# Required feature keys for labeling
REQUIRED_FEATURES = frozenset({
    "delta_price",
    "ema_bias",
    "volatility_state",
    "price",
})


def _required_finite_float(features: Mapping[str, object], key: str, snapshot_name: str) -> float:
    if key not in features:
        raise ValueError(f"{snapshot_name} missing required feature: {key}")
    value = features[key]
    if value is None or isinstance(value, bool):
        raise ValueError(
            f"{snapshot_name} required feature {key} must be a finite number, got {value!r}"
        )
    try:
        if isinstance(value, Real):
            numeric = float(value)
        else:
            numeric = float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{snapshot_name} required feature {key} must be a finite number, got {value!r}"
        ) from exc
    if not math.isfinite(numeric):
        raise ValueError(
            f"{snapshot_name} required feature {key} must be finite, got {value!r}"
        )
    return numeric


class RegimeLabeler:
    """Compute the realized regime from feature snapshots at t and t+H.

    All thresholds are loaded from OracleConfig (regime_oracle_reward.yaml)
    and can be tuned without code changes.

    Feature handling:
        - delta_price is normalized by price to get a symbol-agnostic % change
        - ema_bias is re-centered from [0,1]@0.5 to [-0.5,+0.5]@0
        - volatility_state [0,1] is used directly (replaces missing atr_pct)
    """

    def __init__(
        self,
        high_vol_threshold: float,
        exhaustion_vol_now_threshold: float,
        exhaustion_vol_future_threshold: float,
        trend_delta_pct_threshold: float,
        trend_ema_threshold: float,
        mr_delta_pct_threshold: float,
    ) -> None:
        self.high_vol_threshold = high_vol_threshold
        self.exhaustion_vol_now_threshold = exhaustion_vol_now_threshold
        self.exhaustion_vol_future_threshold = exhaustion_vol_future_threshold
        self.trend_delta_pct_threshold = trend_delta_pct_threshold
        self.trend_ema_threshold = trend_ema_threshold
        self.mr_delta_pct_threshold = mr_delta_pct_threshold

    @classmethod
    def from_config(cls, config) -> "RegimeLabeler":
        """Construct from an OracleConfig instance."""
        return cls(
            high_vol_threshold=config.high_vol_threshold,
            exhaustion_vol_now_threshold=config.exhaustion_vol_now_threshold,
            exhaustion_vol_future_threshold=config.exhaustion_vol_future_threshold,
            trend_delta_pct_threshold=config.trend_delta_pct_threshold,
            trend_ema_threshold=config.trend_ema_threshold,
            mr_delta_pct_threshold=config.mr_delta_pct_threshold,
        )

    def compute_realized_regime(
        self,
        features_t: Mapping[str, object],
        features_t_plus_h: Mapping[str, object],
    ) -> int:
        """Determine what regime actually materialized H bars after time t.

        Uses features available in logs/features/*.log with proper normalization.

        Args:
            features_t: Feature dict at prediction time.
            features_t_plus_h: Feature dict H bars later (realized future).

        Returns:
            Integer regime label (0-4).
        """
        # --- Extract and normalize features ---
        price_now = _required_finite_float(features_t, "price", "features_t")
        if abs(price_now) <= 1e-12:
            raise ValueError(
                "features_t required feature price must be non-zero")

        delta_price_future = _required_finite_float(
            features_t_plus_h, "delta_price", "features_t_plus_h")

        # Normalize delta_price by price to get percentage change
        # This makes thresholds symbol-agnostic (works for BTC at $70k and DOGE at $0.15)
        delta_pct = delta_price_future / price_now

        # Re-center ema_bias from [0,1]@0.5 to [-0.5,+0.5]@0
        ema_bias_future = _required_finite_float(
            features_t_plus_h, "ema_bias", "features_t_plus_h")
        ema_centered = ema_bias_future - 0.5

        # Volatility state: [0,1] where 0=calm, 1=high vol
        # Replaces volatility_atr_pct which doesn't exist in feature logs
        vol_state_now = _required_finite_float(
            features_t, "volatility_state", "features_t")
        vol_state_future = _required_finite_float(
            features_t_plus_h, "volatility_state", "features_t_plus_h")

        # --- Classification cascade (priority order) ---

        # Rule 1: HIGH_VOLATILITY — future vol state is very high
        if vol_state_future > self.high_vol_threshold:
            return HIGH_VOLATILITY

        # Rule 2: EXHAUSTION — vol was high but collapsed to low
        if (vol_state_now > self.exhaustion_vol_now_threshold
                and vol_state_future < self.exhaustion_vol_future_threshold):
            return EXHAUSTION

        # Rule 3: TREND_UP — positive % move + EMA confirmation
        if (delta_pct > self.trend_delta_pct_threshold
                and ema_centered > self.trend_ema_threshold):
            return TREND_UP

        # Rule 4: TREND_DOWN — negative % move + EMA confirmation
        if (delta_pct < -self.trend_delta_pct_threshold
                and ema_centered < -self.trend_ema_threshold):
            return TREND_DOWN

        # Rule 5: MEAN_REVERSION — small percentage moves
        if abs(delta_pct) < self.mr_delta_pct_threshold:
            return MEAN_REVERSION

        # Default fallback: MR (remaining bars with moderate delta but no EMA confirmation)
        return MEAN_REVERSION
