from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class WeightedMeanReversionConfig:
    bb_weight: Decimal
    rsi_weight: Decimal
    sma_weight: Decimal
    stoch_weight: Decimal
    threshold: Decimal
    rsi_oversold: Decimal
    rsi_overbought: Decimal
    sma_deviation_normalizer: Decimal
    stoch_oversold_zone: Decimal
    stoch_overbought_zone: Decimal
    stoch_signal_strength: Decimal
    volume_enabled: bool
    volume_confirm_multiplier: Decimal
    volume_contradict_multiplier: Decimal
    volume_high_threshold: Decimal
    volume_low_threshold: Decimal
    bb_min_width: Decimal
    bb_max_width: Decimal
    bb_narrow_penalty_enabled: bool
    bb_narrow_threshold: Decimal
    bb_narrow_penalty: Decimal
    bb_wide_boost_enabled: bool
    bb_wide_threshold: Decimal
    bb_max_multiplier: Decimal


@dataclass(frozen=True, slots=True)
class WeightedMeanReversionResult:
    allowed: bool
    side: str
    combined_score: Decimal
    final_score: Decimal
    confidence: Decimal
    reason: str
    components: Mapping[str, Decimal]
    weights: Mapping[str, Decimal]
    multipliers: Mapping[str, Decimal]


class WeightedMeanReversionScorer:
    """Pure S01-style weighted mean-reversion scorer."""

    REQUIRED_FEATURES = (
        "bb_position",
        "bb_width",
        "rsi_14",
        "price_sma_20_deviation",
        "volume_sma_ratio",
        "stoch_k",
        "stoch_d",
    )

    def __init__(self, config: WeightedMeanReversionConfig) -> None:
        self.config = config

    def score(self, features: Mapping[str, Any]) -> WeightedMeanReversionResult:
        missing = [key for key in self.REQUIRED_FEATURES if key not in features or features.get(key) is None]
        if missing:
            return self._suppressed(
                reason=f"missing_components:{','.join(missing)}",
                components={},
            )

        try:
            bb_pos = self._decimal(features["bb_position"])
            bb_width = self._decimal(features["bb_width"])
            rsi = self._oscillator_decimal(features["rsi_14"])
            sma_dev = self._decimal(features["price_sma_20_deviation"])
            vol_ratio = self._decimal(features["volume_sma_ratio"])
            stoch_k = self._oscillator_decimal(features["stoch_k"])
            stoch_d = self._oscillator_decimal(features["stoch_d"])
        except Exception as exc:
            return self._suppressed(reason=f"invalid_component:{exc}", components={})

        cfg = self.config
        if bb_width < cfg.bb_min_width:
            return self._suppressed(reason=f"bb_width_too_narrow:{bb_width}", components={})
        if bb_width > cfg.bb_max_width:
            return self._suppressed(reason=f"bb_width_too_wide:{bb_width}", components={})

        bb_signal = (Decimal("0.5") - bb_pos) * Decimal("2")

        rsi_signal = Decimal("0")
        if rsi < cfg.rsi_oversold:
            rsi_signal = Decimal("1.0")
        elif rsi > cfg.rsi_overbought:
            rsi_signal = Decimal("-1.0")

        sma_signal = -(sma_dev / cfg.sma_deviation_normalizer)
        sma_signal = max(Decimal("-1.0"), min(Decimal("1.0"), sma_signal))

        stoch_signal = Decimal("0")
        if stoch_k > stoch_d and stoch_k < cfg.stoch_oversold_zone:
            stoch_signal = cfg.stoch_signal_strength
        elif stoch_k < stoch_d and stoch_k > cfg.stoch_overbought_zone:
            stoch_signal = -cfg.stoch_signal_strength

        weights = {
            "bb": cfg.bb_weight,
            "rsi": cfg.rsi_weight,
            "sma": cfg.sma_weight,
            "stoch": cfg.stoch_weight,
        }
        components = {
            "bb": bb_signal,
            "rsi": rsi_signal,
            "sma": sma_signal,
            "stoch": stoch_signal,
        }
        combined_score = (
            bb_signal * cfg.bb_weight
            + rsi_signal * cfg.rsi_weight
            + sma_signal * cfg.sma_weight
            + stoch_signal * cfg.stoch_weight
        )

        volume_multiplier = Decimal("1.0")
        if cfg.volume_enabled and abs(combined_score) > Decimal("0.2"):
            if vol_ratio > cfg.volume_high_threshold:
                volume_multiplier = cfg.volume_confirm_multiplier
            elif vol_ratio < cfg.volume_low_threshold:
                volume_multiplier = cfg.volume_contradict_multiplier
        combined_score *= volume_multiplier

        volatility_multiplier = Decimal("1.0")
        if cfg.bb_wide_boost_enabled and bb_width > cfg.bb_wide_threshold:
            volatility_multiplier = min(cfg.bb_max_multiplier, bb_width / cfg.bb_wide_threshold)
        elif cfg.bb_narrow_penalty_enabled and bb_width < cfg.bb_narrow_threshold:
            volatility_multiplier = cfg.bb_narrow_penalty
        final_score = max(Decimal("-1.0"), min(Decimal("1.0"), combined_score * volatility_multiplier))

        side = "NEUTRAL"
        if final_score >= cfg.threshold:
            side = "BUY"
        elif final_score <= -cfg.threshold:
            side = "SELL"

        confidence = self._confidence(components)
        allowed = side != "NEUTRAL"
        reason = "threshold_pass" if allowed else f"threshold_suppressed:{final_score}"
        return WeightedMeanReversionResult(
            allowed=allowed,
            side=side,
            combined_score=combined_score,
            final_score=final_score,
            confidence=confidence,
            reason=reason,
            components=components,
            weights=weights,
            multipliers={
                "volume": volume_multiplier,
                "volatility": volatility_multiplier,
            },
        )

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        return Decimal(str(value))

    @classmethod
    def _oscillator_decimal(cls, value: Any) -> Decimal:
        dec = cls._decimal(value)
        if dec <= Decimal("1.0"):
            dec *= Decimal("100.0")
        return dec

    def _confidence(self, components: Mapping[str, Decimal]) -> Decimal:
        signals = list(components.values())
        non_zero = [sig for sig in signals if abs(sig) > Decimal("0.1")]
        if not non_zero:
            return Decimal("0.5")
        positive = sum(1 for sig in non_zero if sig > 0)
        negative = sum(1 for sig in non_zero if sig < 0)
        agreement_ratio = Decimal(str(max(positive, negative))) / Decimal(str(len(non_zero)))
        base_confidence = Decimal("0.5") + (agreement_ratio * Decimal("0.4"))
        avg_strength = sum(abs(sig) for sig in non_zero) / Decimal(str(len(non_zero)))
        strength_factor = min(Decimal("1.2"), Decimal("0.8") + avg_strength)
        return min(Decimal("1.0"), base_confidence * strength_factor)

    @staticmethod
    def _suppressed(
        *,
        reason: str,
        components: Mapping[str, Decimal],
    ) -> WeightedMeanReversionResult:
        return WeightedMeanReversionResult(
            allowed=False,
            side="NEUTRAL",
            combined_score=Decimal("0"),
            final_score=Decimal("0"),
            confidence=Decimal("0"),
            reason=reason,
            components=components,
            weights={},
            multipliers={},
        )
