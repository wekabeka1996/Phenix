"""
Volatility Alpha Model

Calculates alpha score based on volatility patterns and regime changes.
Positive score indicates increasing volatility (potential breakout),
negative indicates decreasing volatility (potential range).
"""

from typing import Dict, Any, Optional
from decimal import Decimal
from ..alpha_model import AlphaModel, AlphaScore


class VolatilityAlphaModel(AlphaModel):
    """
    Volatility-based alpha model.

    Analyzes volatility patterns for trading opportunities:
    - Volatility expansion: potential breakouts
    - Volatility contraction: potential range trading
    - ATR trends: volatility momentum
    - Volume-volatility correlation

    Score indicates volatility-based alpha opportunities.
    """

    def get_model_name(self) -> str:
        return "volatility_v1"

    def get_required_features(self) -> list[str]:
        return [
            'atr_14',           # Average True Range
            'atr_ratio',        # Current ATR vs historical average
            'bb_width',         # Bollinger Band width
            'bb_width_change',  # Change in BB width
            'realized_volatility_1h',  # 1-hour realized volatility
            'realized_volatility_1d',  # 1-day realized volatility
            'volume_volatility_ratio',  # Volume-adjusted volatility
            'price_range_ratio'  # Current range vs average range
        ]

    def calculate_alpha(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        features: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AlphaScore:
        """
        Calculate volatility-based alpha score.

        Formula analyzes volatility patterns:
        - ATR ratio: current vs historical volatility
        - BB width change: expanding/contracting bands
        - Realized volatility trends
        - Volume-volatility correlation

        Positive score = increasing volatility (breakout potential)
        Negative score = decreasing volatility (range potential)
        """

        # Extract features
        atr_ratio = Decimal(str(features["atr_ratio"] if "atr_ratio" in features else 1))
        bb_width = Decimal(str(features["bb_width"] if "bb_width" in features else 0.05))
        bb_width_change = Decimal(str(features["bb_width_change"] if "bb_width_change" in features else 0))
        rv_1h = Decimal(str(features["realized_volatility_1h"] if "realized_volatility_1h" in features else 0))
        rv_1d = Decimal(str(features["realized_volatility_1d"] if "realized_volatility_1d" in features else 0))
        vol_vol_ratio = Decimal(
            str(features["volume_volatility_ratio"] if "volume_volatility_ratio" in features else 1))
        range_ratio = Decimal(str(features["price_range_ratio"] if "price_range_ratio" in features else 1))

        # ATR ratio signal: >1 = higher volatility, <1 = lower volatility
        atr_signal = atr_ratio - Decimal('1.0')  # Center on 0
        atr_clamp = Decimal(str(self.config.get("signal_clamp", {}).get("atr", 2.0)))
        atr_signal = max(-atr_clamp, min(atr_clamp, atr_signal))  # Clamp

        # BB width change signal: positive = expanding, negative = contracting
        bb_cfg = self.config.get("bb", {})
        bb_amplifier = Decimal(str(bb_cfg.get("amplifier", 10)))
        bb_signal = bb_width_change * bb_amplifier  # Amplify small changes
        bb_signal = max(Decimal('-1.0'), min(Decimal('1.0'), bb_signal))

        # Realized volatility trend: 1h vs 1d
        rv_trend = rv_1h - rv_1d  # Positive = increasing vol, negative = decreasing
        rv_signal = Decimal('0')
        if rv_1d > 0:
            rv_signal = rv_trend / rv_1d  # Normalize
        else:
            rv_signal = rv_trend / Decimal('0.001')
        rv_clamp = Decimal(str(self.config.get("signal_clamp", {}).get("rv", 2.0)))
        rv_signal = max(-rv_clamp, min(rv_clamp, rv_signal))

        # Range ratio signal
        range_signal = range_ratio - Decimal('1.0')  # Center on 0
        range_signal = max(Decimal('-1.0'), min(Decimal('1.0'), range_signal))

        # Volume-volatility correlation
        vol_vol_cfg = self.config.get("volume_vol", {})
        vol_vol_high_thresh = Decimal(str(vol_vol_cfg.get("high_threshold", 1.2)))
        vol_vol_low_thresh = Decimal(str(vol_vol_cfg.get("low_threshold", 0.8)))
        vol_vol_sig_strength = Decimal(str(vol_vol_cfg.get("signal_strength", 0.2)))

        vol_corr_signal = Decimal('0')
        if vol_vol_ratio > vol_vol_high_thresh:
            # High volume + high vol = confirmation
            vol_corr_signal = vol_vol_sig_strength
        elif vol_vol_ratio < vol_vol_low_thresh:
            # Low volume + low vol = weak signal
            vol_corr_signal = -vol_vol_sig_strength

        # Combine signals with weights
        weights_cfg = self.config.get("weights", {})
        weights = {
            'atr': Decimal(str(weights_cfg.get('atr', 0.4))),
            'bb': Decimal(str(weights_cfg.get('bb', 0.25))),
            'rv': Decimal(str(weights_cfg.get('rv', 0.2))),
            'range': Decimal(str(weights_cfg.get('range', 0.1))),
            'vol_corr': Decimal(str(weights_cfg.get('vol_corr', 0.05)))
        }

        combined_score = (
            atr_signal * weights['atr'] +
            bb_signal * weights['bb'] +
            rv_signal * weights['rv'] +
            range_signal * weights['range'] +
            vol_corr_signal * weights['vol_corr']
        )

        # Absolute volatility level filter
        vol_level_cfg = self.config.get("vol_level", {})
        vol_low_level = Decimal(str(vol_level_cfg.get("low_level", 0.5)))
        vol_low_penalty = Decimal(str(vol_level_cfg.get("low_penalty", 0.5)))
        vol_high_level = Decimal(str(vol_level_cfg.get("high_level", 2.0)))
        vol_high_boost = Decimal(str(vol_level_cfg.get("high_boost", 1.2)))

        volatility_level = (atr_ratio + bb_width * Decimal('20') + rv_1h) / Decimal('3')
        if volatility_level < vol_low_level:  # Very low volatility
            combined_score *= vol_low_penalty  # Reduce signal strength
        elif volatility_level > vol_high_level:  # Very high volatility
            combined_score *= vol_high_boost  # Amplify signal strength

        # Clamp to [-1, 1]
        final_score = max(Decimal('-1.0'), min(Decimal('1.0'), combined_score))

        # Calculate confidence based on signal consistency
        confidence = self._calculate_confidence(
            atr_signal, bb_signal, rv_signal, range_signal)

        # Build reasoning
        why = self._build_reasoning(
            final_score, atr_ratio, bb_width_change, rv_trend, vol_vol_ratio)

        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=final_score,
            confidence=confidence,
            features_used=self.get_required_features(),
            why=why
        )

    def _calculate_confidence(self, atr_sig: Decimal, bb_sig: Decimal,
                               rv_sig: Decimal, range_sig: Decimal) -> Decimal:
        """Calculate confidence based on signal agreement and strength."""
        signals = [atr_sig, bb_sig, rv_sig, range_sig]

        # Agreement: all signals should have same sign for high confidence
        positive_count = sum(1 for s in signals if s > 0.1)
        negative_count = sum(1 for s in signals if s < -0.1)

        total_strong_signals = positive_count + negative_count
        
        conf_cfg = self.config.get("confidence", {})
        conf_base = Decimal(str(conf_cfg.get("base", 0.6)))
        agreement_factor = Decimal(str(conf_cfg.get("agreement_factor", 0.3)))
        strength_base = Decimal(str(conf_cfg.get("strength_base", 0.7)))
        no_signal_val = Decimal(str(conf_cfg.get("no_signal", 0.4)))

        if total_strong_signals == 0:
            return no_signal_val  # Low confidence if no strong signals

        # Agreement ratio
        agreement_ratio = max(
            positive_count, negative_count) / total_strong_signals

        # Base confidence from agreement
        base_confidence = conf_base + (Decimal(str(agreement_ratio)) * agreement_factor)

        # Strength factor: average absolute signal strength
        avg_strength = sum(abs(s) for s in signals) / len(signals)
        strength_factor = min(Decimal('1.3'), strength_base + Decimal(str(avg_strength)))

        return min(Decimal('1.0'), base_confidence * strength_factor)

    def _build_reasoning(self, score: Decimal, atr_ratio: Decimal,
                         bb_change: Decimal, rv_trend: Decimal, vol_vol_ratio: Decimal) -> list[str]:
        """Build human-readable reasoning for the score."""
        why = []

        if abs(score) < 0.2:
            why.append("Weak or conflicting volatility signals")
            return why

        # ATR analysis
        if atr_ratio > 1.2:
            why.append(
                f"ATR ratio {atr_ratio:.2f} indicates elevated volatility")
        elif atr_ratio < 0.8:
            why.append(f"ATR ratio {atr_ratio:.2f} indicates low volatility")

        # BB width change
        if bb_change > 0.005:
            why.append("Bollinger Bands expanding (volatility increasing)")
        elif bb_change < -0.005:
            why.append("Bollinger Bands contracting (volatility decreasing)")

        # Realized volatility trend
        if rv_trend > 0.01:
            why.append("Realized volatility trending higher")
        elif rv_trend < -0.01:
            why.append("Realized volatility trending lower")

        # Volume-volatility correlation
        if vol_vol_ratio > 1.2:
            why.append("Volume confirms volatility direction")
        elif vol_vol_ratio < 0.8:
            why.append("Volume contradicts volatility direction")

        # Overall interpretation
        if score > 0.3:
            why.append(
                "Strong volatility expansion - potential breakout opportunity")
        elif score < -0.3:
            why.append(
                "Strong volatility contraction - potential range trading")
        elif score > 0:
            why.append("Moderate volatility increase")
        elif score < 0:
            why.append("Moderate volatility decrease")

        return why
