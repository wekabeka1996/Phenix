"""
MD-AMR Alpha Adapter
====================

Lightweight standalone adapter that replicates MD-AMR channel + directional
scoring as an AlphaModel for alpha_search shadow scenarios.

Does NOT import MDAMRStrategyV11 — implements the core formula independently
to avoid live runtime coupling.
"""

import decimal
import math
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..alpha_model import AlphaModel, AlphaScore

LOG = logging.getLogger(__name__)

# Default parameters matching md_amr.yaml production config
_DEFAULTS = {
    "channel_window_bars": 12,
    "atr_window": 14,
    "atr_stats_window": 64,
    "hysteresis_mult": 1.2,
    "threshold_z": 2.2,
    "volatility_dampening_factor": 0.5,
    "thr_base": 0.55,
    "thr_floor": 0.1,
    "alpha": 0.25,
    "atr_zscore_clamp": 10.0,
    "atr_std_floor_pct": 0.05,
    "weights": {
        "d1": 0.35,
        "h1": 0.30,
        "m30": 0.20,
        "m15": 0.15,
    },
}

# Lookback bars for each timeframe component (at 15m = 900s per bar)
_TF_LOOKBACKS = {
    "d1": 96,   # ~1 day
    "h1": 4,    # ~1 hour
    "m30": 2,   # ~30 min
    "m15": 1,   # ~15 min
}


@dataclass
class _SymbolState:
    """Per-symbol OHLC and ATR state for the MD-AMR adapter."""
    closes: deque = field(default_factory=lambda: deque(maxlen=200))
    highs: deque = field(default_factory=lambda: deque(maxlen=200))
    lows: deque = field(default_factory=lambda: deque(maxlen=200))
    atr_history: deque = field(default_factory=lambda: deque(maxlen=64))
    bar_count: int = 0


class MdAmrAlphaAdapter(AlphaModel):
    """
    MD-AMR channel scoring adapter for alpha_search.

    Replicates the core MDAMRStrategyV11 entry scoring formula:
    1. Compute avg OHLC channel
    2. Compute ATR + ATR z-score
    3. Compute multi-TF directional components
    4. Apply weight dampening in high volatility
    5. Compute threshold deformation
    6. Compute channel score
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        # Merge user config over defaults BEFORE super().__init__()
        # because super().__init__() calls get_model_name() which needs self
        merged = {**_DEFAULTS, **(config or {})}
        self._cfg = merged
        self._weights = {**_DEFAULTS["weights"], **merged.get("weights", {})}
        self._states: Dict[str, _SymbolState] = {}
        self._min_bars = max(
            self._cfg["channel_window_bars"],
            self._cfg["atr_window"],
            max(_TF_LOOKBACKS.values()) + 1,
        )
        super().__init__(config or {})

    def get_model_name(self) -> str:
        return "md_amr_channel"

    def get_required_features(self) -> List[str]:
        return ["close", "high", "low"]

    def calculate_alpha(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        features: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> AlphaScore:
        """
        Calculate alpha using MD-AMR channel + directional scoring.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            market_data: Market data with OHLCV bars
            features: Pre-calculated features from FE
            context: Optional context with 'regime' etc.

        Returns:
            AlphaScore with MD-AMR-computed signal
        """
        state = self._states.setdefault(symbol, _SymbolState())

        # Extract price from market_data then features
        close = self._get_price(market_data, features)
        if close <= 0:
            return self._fail_closed_score(
                symbol,
                reason="missing_price",
                why=["No valid price in market_data or features"],
            )

        # Extract high/low from market_data or features
        high = self._extract_value(market_data, features, ["bar_high", "high"], close)
        low = self._extract_value(market_data, features, ["bar_low", "low"], close)

        # Accumulate bars
        state.closes.append(close)
        state.highs.append(high)
        state.lows.append(low)
        state.bar_count += 1

        # Check warmup
        if state.bar_count < self._min_bars:
            return AlphaScore(
                model_name=self.get_model_name(),
                symbol=symbol,
                score=decimal.Decimal("0"),
                confidence=decimal.Decimal("0"),
                features_used=["close", "high", "low"],
                why=[f"warmup:{state.bar_count}/{self._min_bars}"],
            )

        why: List[str] = []

        # 1. Compute avg OHLC channel
        cw = self._cfg["channel_window_bars"]
        recent_highs = list(state.highs)[-cw:]
        recent_lows = list(state.lows)[-cw:]
        recent_closes = list(state.closes)[-cw:]
        avg_high = sum(recent_highs) / len(recent_highs)
        avg_low = sum(recent_lows) / len(recent_lows)

        # 2. Compute ATR
        atr = self._compute_atr(state)
        state.atr_history.append(atr)

        # 3. ATR z-score
        atr_zscore = self._compute_atr_zscore(state)

        # 4. Directional components: tanh(return * 6) for each lookback
        dir_components: Dict[str, float] = {}
        closes_list = list(state.closes)
        for tf_name, lookback in _TF_LOOKBACKS.items():
            if len(closes_list) > lookback:
                prev = closes_list[-1 - lookback]
                ret = (closes_list[-1] - prev) / max(prev, 1e-10)
                dir_components[tf_name] = math.tanh(ret * 6.0)
            else:
                dir_components[tf_name] = 0.0

        # 5. Weight dampening in high volatility
        weights = dict(self._weights)
        if atr_zscore > self._cfg["threshold_z"]:
            dampening = self._cfg["volatility_dampening_factor"]
            weights["d1"] *= dampening
            weights["h1"] *= dampening
            why.append(f"vol_dampened:z={atr_zscore:.2f}")

        # Normalize weights
        w_sum = sum(weights.values())
        if w_sum > 0:
            weights = {k: v / w_sum for k, v in weights.items()}

        # 6. Directional score = weighted sum of components
        dir_score = sum(
            dir_components.get(k, 0.0) * weights.get(k, 0.0) for k in weights
        )
        dir_score = max(-1.0, min(1.0, dir_score))

        # 7. Threshold deformation
        alpha_val = self._cfg["alpha"]
        thr_base = self._cfg["thr_base"]
        thr_floor = self._cfg["thr_floor"]
        bias = alpha_val * abs(dir_score)

        if dir_score >= 0:
            thr_buy = max(thr_floor, min(0.99, thr_base - bias))
            thr_sell = max(thr_floor, min(0.99, thr_base + bias))
        else:
            thr_buy = max(thr_floor, min(0.99, thr_base + bias))
            thr_sell = max(thr_floor, min(0.99, thr_base - bias))

        # 8. Channel score
        band = max(avg_high - avg_low, 1e-10)
        hysteresis = self._cfg["hysteresis_mult"]
        long_score = max(0.0, (avg_low - close) / band) * hysteresis
        short_score = max(0.0, (close - avg_high) / band) * hysteresis
        score = max(-1.0, min(1.0, long_score - short_score))

        # Determine side via threshold comparison
        if score >= thr_buy:
            why.append(f"channel_long:score={score:.4f}>=thr={thr_buy:.4f}")
        elif score <= -thr_sell:
            why.append(f"channel_short:score={score:.4f}<=-thr={thr_sell:.4f}")
        else:
            why.append(
                f"no_signal:score={score:.4f},"
                f"thr_buy={thr_buy:.4f},thr_sell={thr_sell:.4f}"
            )

        why.append(f"dir={dir_score:.4f}")
        why.append(f"atr_z={atr_zscore:.2f}")

        # Confidence: absolute score magnitude scaled up, clamped to [0, 1]
        confidence = min(1.0, abs(score) * 1.5)

        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=decimal.Decimal(str(round(score, 6))),
            confidence=decimal.Decimal(str(round(confidence, 4))),
            features_used=["close", "high", "low"],
            why=why,
        )

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_price(
        market_data: Dict[str, Any], features: Dict[str, Any]
    ) -> float:
        """Extract price from market_data or features."""
        for src in (market_data, features):
            for key in ("close", "bar_close", "price", "last_price"):
                val = src.get(key)
                if val is not None:
                    try:
                        p = float(val)
                        if p > 0:
                            return p
                    except (ValueError, TypeError):
                        pass
        return 0.0

    @staticmethod
    def _extract_value(
        market_data: Dict[str, Any],
        features: Dict[str, Any],
        keys: List[str],
        fallback: float,
    ) -> float:
        """Extract a numeric value from market_data/features by key priority."""
        for src in (market_data, features):
            for k in keys:
                val = src.get(k)
                if val is not None:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
        return fallback

    def _fail_closed_score(
        self, symbol: str, reason: str, why: List[str]
    ) -> AlphaScore:
        """Return fail-closed score (0 with explanation)."""
        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=decimal.Decimal("0"),
            confidence=decimal.Decimal("0"),
            features_used=[],
            why=[f"fail_closed:{reason}"] + why,
        )

    def _compute_atr(self, state: _SymbolState) -> float:
        """Compute ATR from recent highs/lows/closes."""
        window = self._cfg["atr_window"]
        highs = list(state.highs)[-(window + 1):]
        lows = list(state.lows)[-(window + 1):]
        closes = list(state.closes)[-(window + 1):]

        if len(closes) < 2:
            return 0.0

        true_ranges = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            true_ranges.append(tr)

        if not true_ranges:
            return 0.0
        return sum(true_ranges) / len(true_ranges)

    def _compute_atr_zscore(self, state: _SymbolState) -> float:
        """Compute ATR z-score from ATR history."""
        if len(state.atr_history) < 2:
            return 0.0

        atrs = list(state.atr_history)
        mean_atr = sum(atrs) / len(atrs)
        if mean_atr == 0:
            return 0.0

        variance = sum((a - mean_atr) ** 2 for a in atrs) / (len(atrs) - 1)
        std_atr = math.sqrt(variance) if variance > 0 else 0.0
        std_floor = mean_atr * self._cfg["atr_std_floor_pct"]
        effective_std = max(std_atr, std_floor)

        current_atr = atrs[-1]
        zscore = (current_atr - mean_atr) / effective_std
        clamp = self._cfg["atr_zscore_clamp"]
        return max(-clamp, min(clamp, zscore))
