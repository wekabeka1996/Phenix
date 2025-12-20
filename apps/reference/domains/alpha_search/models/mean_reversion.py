"""
Mean Reversion Alpha Model

Calculates alpha score based on deviation from moving averages and Bollinger Bands.
Positive score indicates potential reversion to mean (buy signal),
negative indicates overextension (sell signal).
"""

from typing import Dict, Any, Optional
from decimal import Decimal
from ..alpha_model import AlphaModel, AlphaScore


class MeanReversionAlphaModel(AlphaModel):
    """
    Mean reversion-based alpha model.

    Identifies overbought/oversold conditions using:
    - Bollinger Band position (%B)
    - RSI divergence
    - Moving average deviations
    - Volume confirmation for reversions

    Score indicates strength of mean reversion signal.
    """

    def get_model_name(self) -> str:
        return "mean_reversion_v1"

    def get_required_features(self) -> list[str]:
        return [
            'bb_position',  # %B - position within Bollinger Bands [0,1]
            'bb_width',     # Bollinger Band width (volatility measure)
            'rsi_14',
            'price_sma_20_deviation',  # Deviation from 20-period SMA
            'volume_sma_ratio',        # Current volume vs SMA volume
            'stoch_k',      # Stochastic %K
            'stoch_d'       # Stochastic %D
        ]

    def calculate_alpha(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        features: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AlphaScore:
        """
        Calculate mean reversion alpha score.

        Formula combines multiple reversion signals:
        - BB position: 0 = lower band (buy), 1 = upper band (sell)
        - RSI: <30 = oversold (buy), >70 = overbought (sell)
        - SMA deviation: negative = below mean (buy), positive = above mean (sell)
        - Stochastic: crossover signals

        Score = weighted combination of normalized signals
        """

        # Extract features
        bb_pos = Decimal(str(features["bb_position"] if "bb_position" in features else 0.5))
        bb_width = Decimal(str(features["bb_width"] if "bb_width" in features else 0.1))
        rsi = Decimal(str(features["rsi_14"] if "rsi_14" in features else 50))
        sma_dev = Decimal(str(features["price_sma_20_deviation"] if "price_sma_20_deviation" in features else 0))
        vol_ratio = Decimal(str(features["volume_sma_ratio"] if "volume_sma_ratio" in features else 1))
        stoch_k = Decimal(str(features["stoch_k"] if "stoch_k" in features else 50))
        stoch_d = Decimal(str(features["stoch_d"] if "stoch_d" in features else 50))

        # BB position signal: 0 = lower band (strong buy), 1 = upper band (strong sell)
        # Convert to [-1, 1] where -1 = strong buy, +1 = strong sell
        bb_signal = (bb_pos - Decimal('0.5')) * \
            Decimal('2')  # [0,1] -> [-1,1] centered on 0

        # RSI signal: <30 = oversold (buy), >70 = overbought (sell)
        rsi_signal = Decimal('0')
        if rsi < 30:
            rsi_signal = -Decimal('1.0')  # Strong buy
        elif rsi > 70:
            rsi_signal = Decimal('1.0')  # Strong sell

        # SMA deviation signal: negative deviation = below mean (buy), positive = above (sell)
        # Normalize by typical 5% deviation
        sma_signal = sma_dev / Decimal('0.05')
        sma_signal = max(Decimal('-1.0'), min(Decimal('1.0'), sma_signal))

        # Stochastic signal: %K crossing %D
        stoch_signal = Decimal('0')
        if stoch_k > stoch_d and stoch_k < 20:  # %K crosses above %D in oversold
            stoch_signal = -Decimal('0.3')
        elif stoch_k < stoch_d and stoch_k > 80:  # %K crosses below %D in overbought
            stoch_signal = Decimal('0.3')

        # Combine signals with weights
        weights = {
            'bb': Decimal('0.4'),
            'rsi': Decimal('0.3'),
            'sma': Decimal('0.2'),
            'stoch': Decimal('0.1')
        }

        combined_score = (
            bb_signal * weights['bb'] +
            rsi_signal * weights['rsi'] +
            sma_signal * weights['sma'] +
            stoch_signal * weights['stoch']
        )

        # Volume confirmation: higher volume strengthens reversion signals
        volume_multiplier = Decimal('1.0')
        if abs(combined_score) > 0.2 and vol_ratio > 1.5:
            volume_multiplier = Decimal('1.2')
        elif abs(combined_score) > 0.2 and vol_ratio < 0.7:
            volume_multiplier = Decimal('0.8')

        combined_score *= volume_multiplier

        # BB width filter: wider bands = higher volatility = stronger signals
        volatility_multiplier = Decimal('1.0')
        if bb_width > 0.05:  # Wider than 5%
            volatility_multiplier = min(
                Decimal('1.5'), bb_width / Decimal('0.05'))
        elif bb_width < 0.02:  # Too narrow bands = weak signals
            volatility_multiplier = Decimal('0.7')

        combined_score *= volatility_multiplier

        # Clamp to [-1, 1]
        final_score = max(Decimal('-1.0'), min(Decimal('1.0'), combined_score))

        # Calculate confidence based on signal agreement and strength
        confidence = self._calculate_confidence(
            bb_signal, rsi_signal, sma_signal, stoch_signal)

        # Build reasoning
        why = self._build_reasoning(
            final_score, bb_pos, rsi, sma_dev, vol_ratio)

        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=final_score,
            confidence=confidence,
            features_used=self.get_required_features(),
            why=why
        )

    def _calculate_confidence(self, bb_sig: Decimal, rsi_sig: Decimal,
                              sma_sig: Decimal, stoch_sig: Decimal) -> Decimal:
        """Calculate confidence based on signal agreement."""
        signals = [bb_sig, rsi_sig, sma_sig, stoch_sig]
        non_zero_signals = [s for s in signals if abs(s) > 0.1]

        if not non_zero_signals:
            return Decimal('0.3')  # Low confidence if no strong signals

        # Check agreement: all signals should have same sign
        positive_signals = sum(1 for s in non_zero_signals if s > 0)
        negative_signals = sum(1 for s in non_zero_signals if s < 0)

        agreement_ratio = max(
            positive_signals, negative_signals) / len(non_zero_signals)

        # Base confidence from agreement
        base_confidence = Decimal(
            '0.5') + (Decimal(str(agreement_ratio)) * Decimal('0.4'))

        # Strength factor
        avg_strength = sum(abs(s)
                           for s in non_zero_signals) / len(non_zero_signals)
        strength_factor = min(Decimal('1.2'), Decimal('0.8') + avg_strength)

        return min(Decimal('1.0'), base_confidence * strength_factor)

    def _build_reasoning(self, score: Decimal, bb_pos: Decimal, rsi: Decimal,
                         sma_dev: Decimal, vol_ratio: Decimal) -> list[str]:
        """Build human-readable reasoning for the score."""
        why = []

        if abs(score) < 0.2:
            why.append("Weak or conflicting mean reversion signals")
            return why

        # BB analysis
        if bb_pos < 0.2:
            why.append("Price near lower Bollinger Band (oversold)")
        elif bb_pos > 0.8:
            why.append("Price near upper Bollinger Band (overbought)")

        # RSI analysis
        if rsi < 30:
            why.append(f"RSI at {rsi:.1f} indicates oversold conditions")
        elif rsi > 70:
            why.append(f"RSI at {rsi:.1f} indicates overbought conditions")

        # SMA analysis
        if sma_dev < -0.02:
            why.append("Price significantly below SMA (potential reversion up)")
        elif sma_dev > 0.02:
            why.append(
                "Price significantly above SMA (potential reversion down)")

        # Volume analysis
        if vol_ratio > 1.5:
            why.append("High volume supports potential reversion")
        elif vol_ratio < 0.7:
            why.append("Low volume weakens reversion signal")

        # Overall direction
        if score > 0.3:
            why.append("Strong sell signal - expect downward reversion")
        elif score < -0.3:
            why.append("Strong buy signal - expect upward reversion")
        elif score > 0:
            why.append("Moderate sell signal")
        elif score < 0:
            why.append("Moderate buy signal")

        return why
