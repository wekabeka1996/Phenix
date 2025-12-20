"""
Momentum Alpha Model

Calculates alpha score based on price momentum over multiple timeframes.
Positive score indicates upward momentum, negative indicates downward.
"""

from typing import Dict, Any, Optional
from decimal import Decimal
from ..alpha_model import AlphaModel, AlphaScore


class MomentumAlphaModel(AlphaModel):
    """
    Momentum-based alpha model.

    Analyzes price momentum across multiple timeframes:
    - Short-term (5-15 min): Immediate momentum
    - Medium-term (1-4 hours): Trend direction
    - Long-term (1 day): Overall trend

    Score combines weighted momentum signals with confidence based on consistency.
    """

    def get_model_name(self) -> str:
        return "momentum_v1"

    def get_required_features(self) -> list[str]:
        return [
            'price_momentum_5m',
            'price_momentum_1h',
            'price_momentum_1d',
            'volume_momentum_5m',
            'rsi_14',
            'macd_signal'
        ]

    def calculate_alpha(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        features: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AlphaScore:
        """
        Calculate momentum-based alpha score.

        Formula:
        - Short momentum (30%): 5m momentum
        - Medium momentum (40%): 1h momentum
        - Long momentum (30%): 1d momentum
        - Volume confirmation: amplifies signal if volume supports price
        - RSI filter: reduces confidence in overbought/oversold conditions
        """

        # Extract momentum features
        mom_5m = Decimal(str(features["price_momentum_5m"] if "price_momentum_5m" in features else 0))
        mom_1h = Decimal(str(features["price_momentum_1h"] if "price_momentum_1h" in features else 0))
        mom_1d = Decimal(str(features["price_momentum_1d"] if "price_momentum_1d" in features else 0))
        vol_mom_5m = Decimal(str(features["volume_momentum_5m"] if "volume_momentum_5m" in features else 0))
        rsi = Decimal(str(features["rsi_14"] if "rsi_14" in features else 50))
        macd_signal = Decimal(str(features["macd_signal"] if "macd_signal" in features else 0))

        # Calculate weighted momentum score
        short_weight = Decimal('0.3')
        medium_weight = Decimal('0.4')
        long_weight = Decimal('0.3')

        momentum_score = (
            mom_5m * short_weight +
            mom_1h * medium_weight +
            mom_1d * long_weight
        )

        # Volume confirmation (amplifies signal if volume supports direction)
        volume_multiplier = Decimal('1.0')
        if momentum_score > 0 and vol_mom_5m > 0:
            volume_multiplier = Decimal('1.2')  # Volume supports upward move
        elif momentum_score < 0 and vol_mom_5m < 0:
            volume_multiplier = Decimal('1.2')  # Volume supports downward move
        elif momentum_score != 0 and vol_mom_5m * momentum_score < 0:
            volume_multiplier = Decimal('0.8')  # Volume contradicts price

        momentum_score *= volume_multiplier

        # RSI-based confidence adjustment
        rsi_confidence = Decimal('1.0')
        if rsi > 70:  # Overbought
            rsi_confidence = Decimal('0.7')
        elif rsi < 30:  # Oversold
            rsi_confidence = Decimal('0.7')

        # MACD confirmation
        macd_confidence = Decimal('1.0')
        if (momentum_score > 0 and macd_signal > 0) or (momentum_score < 0 and macd_signal < 0):
            macd_confidence = Decimal('1.1')
        elif macd_signal * momentum_score < 0:
            macd_confidence = Decimal('0.9')

        # Overall confidence based on signal consistency and filters
        base_confidence = Decimal('0.8')  # Base confidence
        consistency_factor = self._calculate_consistency(
            mom_5m, mom_1h, mom_1d)

        confidence = min(Decimal('1.0'), base_confidence *
                         rsi_confidence * macd_confidence * consistency_factor)

        # Clamp score to [-1, 1]
        final_score = max(Decimal('-1.0'), min(Decimal('1.0'), momentum_score))

        # Build reasoning
        why = []
        if final_score > 0.1:
            why.append("Moderate upward momentum")
        elif final_score > 0.01:
            why.append("Weak upward momentum")
        elif final_score < -0.1:
            why.append("Moderate downward momentum")
        elif final_score < -0.01:
            why.append("Weak downward momentum")
        else:
            why.append("Neutral momentum, no clear direction")

        if volume_multiplier > 1:
            why.append("Volume confirms momentum direction")
        elif volume_multiplier < 1:
            why.append("Volume contradicts momentum direction")

        if rsi_confidence < 1:
            why.append(f"RSI at {rsi:.1f} reduces confidence")

        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=final_score,
            confidence=confidence,
            features_used=self.get_required_features(),
            why=why
        )

    def _calculate_consistency(self, mom_5m: Decimal, mom_1h: Decimal, mom_1d: Decimal) -> Decimal:
        """
        Calculate consistency factor based on alignment of momentum signals.
        Returns multiplier [0.7, 1.3] based on how well signals agree.
        """
        # Count agreements
        agreements = 0
        total_pairs = 3  # 5m-1h, 5m-1d, 1h-1d

        # 5m vs 1h
        if (mom_5m > 0 and mom_1h > 0) or (mom_5m < 0 and mom_1h < 0):
            agreements += 1

        # 5m vs 1d
        if (mom_5m > 0 and mom_1d > 0) or (mom_5m < 0 and mom_1d < 0):
            agreements += 1

        # 1h vs 1d
        if (mom_1h > 0 and mom_1d > 0) or (mom_1h < 0 and mom_1d < 0):
            agreements += 1

        consistency_ratio = Decimal(
            str(agreements)) / Decimal(str(total_pairs))

        # Map to multiplier: 0% agreement = 0.7x, 100% agreement = 1.3x
        return Decimal('0.7') + (consistency_ratio * Decimal('0.6'))
