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
        
        rsi_val = features.get("rsi_14", 50)
        if isinstance(rsi_val, (int, float, str)) and float(rsi_val) <= 1.0:
            rsi_val = float(rsi_val) * 100.0
        rsi = Decimal(str(rsi_val))
        
        sma_dev = Decimal(str(features["price_sma_20_deviation"] if "price_sma_20_deviation" in features else 0))
        vol_ratio = Decimal(str(features["volume_sma_ratio"] if "volume_sma_ratio" in features else 1))
        
        stoch_k_val = features.get("stoch_k", 50)
        if isinstance(stoch_k_val, (int, float, str)) and float(stoch_k_val) <= 1.0:
            stoch_k_val = float(stoch_k_val) * 100.0
        stoch_k = Decimal(str(stoch_k_val))
        
        stoch_d_val = features.get("stoch_d", 50)
        if isinstance(stoch_d_val, (int, float, str)) and float(stoch_d_val) <= 1.0:
            stoch_d_val = float(stoch_d_val) * 100.0
        stoch_d = Decimal(str(stoch_d_val))

        # BB position signal: 0 = lower band (strong buy), 1 = upper band (strong sell)
        # Convert to [1, -1] where +1 = strong buy, -1 = strong sell
        bb_signal = (Decimal('0.5') - bb_pos) * Decimal('2')  # [0,1] -> [1,-1] centered on 0

        # RSI signal: < oversold = oversold (buy), > overbought = overbought (sell)
        rsi_oversold = Decimal(str(self.config.get("rsi", {}).get("oversold", 30)))
        rsi_overbought = Decimal(str(self.config.get("rsi", {}).get("overbought", 70)))
        
        rsi_signal = Decimal('0')
        if rsi < rsi_oversold:
            rsi_signal = Decimal('1.0')  # Strong buy
        elif rsi > rsi_overbought:
            rsi_signal = -Decimal('1.0')  # Strong sell

        # SMA deviation signal: negative deviation = below mean (buy), positive = above (sell)
        # Normalize by typical deviation_normalizer
        sma_dev_normalizer = Decimal(str(self.config.get("sma", {}).get("deviation_normalizer", 0.05)))
        sma_signal = Decimal('0')
        if sma_dev_normalizer > 0:
            sma_signal = -(sma_dev / sma_dev_normalizer)
            sma_signal = max(Decimal('-1.0'), min(Decimal('1.0'), sma_signal))

        # Stochastic signal: %K crossing %D
        stoch_oversold_zone = Decimal(str(self.config.get("stochastic", {}).get("oversold_zone", 20)))
        stoch_overbought_zone = Decimal(str(self.config.get("stochastic", {}).get("overbought_zone", 80)))
        stoch_signal_strength = Decimal(str(self.config.get("stochastic", {}).get("signal_strength", 0.3)))
        
        stoch_signal = Decimal('0')
        if stoch_k > stoch_d and stoch_k < stoch_oversold_zone:  # %K crosses above %D in oversold
            stoch_signal = stoch_signal_strength
        elif stoch_k < stoch_d and stoch_k > stoch_overbought_zone:  # %K crosses below %D in overbought
            stoch_signal = -stoch_signal_strength

        # Combine signals with weights
        weights_cfg = self.config.get("weights", {})
        weights = {
            'bb': Decimal(str(weights_cfg.get('bb', 0.4))),
            'rsi': Decimal(str(weights_cfg.get('rsi', 0.3))),
            'sma': Decimal(str(weights_cfg.get('sma', 0.2))),
            'stoch': Decimal(str(weights_cfg.get('stoch', 0.1)))
        }

        combined_score = (
            bb_signal * weights['bb'] +
            rsi_signal * weights['rsi'] +
            sma_signal * weights['sma'] +
            stoch_signal * weights['stoch']
        )

        # Volume confirmation: higher volume strengthens reversion signals
        vol_cfg = self.config.get("volume", {})
        vol_confirm_mult = Decimal(str(vol_cfg.get("confirm_multiplier", 1.2)))
        vol_contradict_mult = Decimal(str(vol_cfg.get("contradict_multiplier", 0.8)))
        vol_high_thresh = Decimal(str(vol_cfg.get("high_threshold", 1.5)))
        vol_low_thresh = Decimal(str(vol_cfg.get("low_threshold", 0.7)))

        volume_multiplier = Decimal('1.0')
        if abs(combined_score) > Decimal('0.2') and vol_ratio > vol_high_thresh:
            volume_multiplier = vol_confirm_mult
        elif abs(combined_score) > Decimal('0.2') and vol_ratio < vol_low_thresh:
            volume_multiplier = vol_contradict_mult

        combined_score *= volume_multiplier

        # BB width filter: wider bands = higher volatility = stronger signals
        bb_width_cfg = self.config.get("bb_width", {})
        bb_wide_thresh = Decimal(str(bb_width_cfg.get("wide_threshold", 0.05)))
        bb_narrow_thresh = Decimal(str(bb_width_cfg.get("narrow_threshold", 0.02)))
        bb_max_mult = Decimal(str(bb_width_cfg.get("max_multiplier", 1.5)))
        bb_narrow_penalty = Decimal(str(bb_width_cfg.get("narrow_penalty", 0.7)))

        volatility_multiplier = Decimal('1.0')
        if bb_width > bb_wide_thresh:  # Wider than 5%
            if bb_wide_thresh > 0:
                volatility_multiplier = min(
                    bb_max_mult, bb_width / bb_wide_thresh)
            else:
                volatility_multiplier = bb_max_mult
        elif bb_width < bb_narrow_thresh:  # Too narrow bands = weak signals
            volatility_multiplier = bb_narrow_penalty

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
        
        conf_cfg = self.config.get("confidence", {})
        base_conf = Decimal(str(conf_cfg.get("base", 0.5)))
        agreement_factor = Decimal(str(conf_cfg.get("agreement_factor", 0.4)))
        strength_base = Decimal(str(conf_cfg.get("strength_base", 0.8)))
        sig_threshold = Decimal(str(conf_cfg.get("signal_threshold", 0.1)))

        non_zero_signals = [s for s in signals if abs(s) > sig_threshold]

        if not non_zero_signals:
            return base_conf  # Low confidence if no strong signals

        # Check agreement: all signals should have same sign
        positive_signals = sum(1 for s in non_zero_signals if s > 0)
        negative_signals = sum(1 for s in non_zero_signals if s < 0)

        agreement_ratio = max(
            positive_signals, negative_signals) / len(non_zero_signals)

        # Base confidence from agreement
        base_confidence = base_conf + (Decimal(str(agreement_ratio)) * agreement_factor)

        # Strength factor
        avg_strength = sum(abs(s)
                           for s in non_zero_signals) / len(non_zero_signals)
        strength_factor = min(Decimal('1.2'), strength_base + avg_strength)

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
            why.append("Strong buy signal - expect upward reversion")
        elif score < -0.3:
            why.append("Strong sell signal - expect downward reversion")
        elif score > 0:
            why.append("Moderate buy signal")
        elif score < 0:
            why.append("Moderate sell signal")

        return why
