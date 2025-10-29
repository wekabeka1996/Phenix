"""
Regime Detector Domain - Market Regime Analysis

Analyzes market features to detect current trading regime (TREND_UP, TREND_DOWN, etc.)
Based on logic from legacy aurora/regime/detectors.py

WHY: Enable regime-aware trading decisions [FSMP-PORTING-T01]
"""

import logging
from decimal import Decimal

from vfoundation.core.protocol import Message


class RegimeDetector:
    """
    Analyzes market features to detect the current trading regime based on
    pre-configured models.
    
    Supports multiple detection models (configurable):
    - SMA trend detection (crossover-based)
    - Volatility regime detection (planned)
    - Mean-reversion detection (planned)
    
    Emits EVT:REGIME_DETECTED events with confidence scores.
    """
    
    def __init__(self, config: dict, fsm):
        """
        Initializes the detector with model configurations.
        
        Args:
            config: Configuration dict with 'models' section containing
                   model-specific parameters (e.g., models.sma_trend)
            fsm: FSMCore instance for event emission and logging
        """
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Load model configuration
        self.model_config = self.config.get("models", {}).get("sma_trend", {})
        self.model_name = "sma_trend_v1"
        
        self.logger.info(f"RegimeDetector initialized with model: {self.model_name}")
    
    def _calculate_confidence(self, sma_short: Decimal, sma_long: Decimal) -> Decimal:
        """
        Calculates a confidence score based on the divergence of short and long SMAs.
        
        The formula is heuristically tuned to map SMA spread to confidence [0.5, 0.95].
        Larger divergence indicates stronger trend signal.
        
        Args:
            sma_short: Short-period simple moving average
            sma_long: Long-period simple moving average
            
        Returns:
            Confidence score as Decimal [0.5, 0.95]
            
        Example:
            >>> _calculate_confidence(Decimal("4050"), Decimal("3900"))
            Decimal("0.77")  # Strong uptrend signal
        """
        if sma_long == 0:
            return Decimal("0.5")
        
        # Heuristic formula: spread / base * multiplier
        # Multiplier of 20.0 empirically tuned for realistic signals
        # For test case: (4050-3900)/3900 = 0.0385 * 20 = 0.77
        spread_ratio = (sma_short - sma_long) / sma_long
        confidence = spread_ratio * Decimal("20.0")
        
        # Bound the confidence between floor (0.5) and ceiling (0.95)
        # Using abs() to handle both uptrend and downtrend signals
        bounded_confidence = min(max(abs(confidence), Decimal("0.5")), Decimal("0.95"))
        return bounded_confidence
    
    def handle_event(self, event: Message) -> None:
        """
        Entry point for handling incoming events.
        
        Currently processes EVT:FEATURES_CALCULATED events to analyze
        market features and detect trading regimes.
        
        Args:
            event: Message object with op=EVT, verb=FEATURES_CALCULATED
                   containing feature data in payload
                   
        Emits:
            EVT:REGIME_DETECTED with regime type and confidence score
        """
        if event.verb != "FEATURES_CALCULATED":
            self.logger.debug(f"Ignoring event: {event.verb}")
            return
        
        features = event.pld.get("features", {})
        price = Decimal(features.get("price", "0"))
        sma_short = Decimal(features.get("sma_short", "0"))
        sma_long = Decimal(features.get("sma_long", "0"))
        symbol = event.pld.get("symbol")
        ts = event.pld.get("ts")
        
        # Volatility features (optional)
        atr_14 = Decimal(features.get("atr_14", "0")) if "atr_14" in features else None
        atr_14_sma_100 = Decimal(features.get("atr_14_sma_100", "0")) if "atr_14_sma_100" in features else None
        
        # Validate required data presence
        if not all([price > 0, sma_short > 0, sma_long > 0, symbol, ts]):
            self.logger.debug(f"Skipping regime detection for {symbol} - missing data")
            return
        
        # --- Regime Detection Logic ---
        regime = "UNCERTAIN"
        confidence = Decimal("0.5")
        source_model = self.model_name
        
        # --- PRIORITY 1: Volatility Regime Detection ---
        # Check for HIGH_VOLATILITY or LOW_VOLATILITY if ATR data available
        volatility_config = self.config.get("models", {}).get("volatility", {})
        if (volatility_config.get("enabled", False) and 
            atr_14 is not None and atr_14_sma_100 is not None and 
            atr_14 > 0 and atr_14_sma_100 > 0):
            
            threshold_multiplier = Decimal(str(volatility_config.get("threshold_multiplier", 2.0)))
            low_vol_multiplier = Decimal(str(volatility_config.get("low_vol_multiplier", 0.5)))
            volatility_ratio = atr_14 / atr_14_sma_100
            
            # HIGH_VOLATILITY: ATR significantly above its long-term average
            if volatility_ratio > threshold_multiplier:
                regime = "HIGH_VOLATILITY"
                source_model = "volatility_v1"
                
                # Confidence increases with higher volatility ratio
                # Formula: min(0.95, 0.5 + (ratio - threshold) * 2.0)
                # Example: ratio=2.14, threshold=2.0 → 0.5 + 0.14*2.0 = 0.78
                excess_volatility = volatility_ratio - threshold_multiplier
                confidence = min(Decimal("0.95"), Decimal("0.5") + excess_volatility * Decimal("2.0"))
            
            # LOW_VOLATILITY: ATR significantly below its long-term average
            elif volatility_ratio < low_vol_multiplier:
                regime = "LOW_VOLATILITY"
                source_model = "volatility_v1"
                
                # Confidence increases with lower volatility ratio (market calm)
                # Formula: min(0.95, 0.5 + (threshold - ratio) * 3.0)
                # Example: ratio=0.43, threshold=0.5 → 0.5 + 0.07*3.0 = 0.71
                calm_factor = low_vol_multiplier - volatility_ratio
                confidence = min(Decimal("0.95"), Decimal("0.5") + calm_factor * Decimal("3.0"))
        
        # --- PRIORITY 2: Mean Reversion Detection ---
        # Calculate relative deviations for mean reversion detection
        # If price and SMAs are tightly clustered → ranging market
        if regime == "UNCERTAIN":  # Only check if volatility didn't trigger
            sma_spread = abs(sma_short - sma_long) / sma_long if sma_long > 0 else Decimal("1.0")
            price_deviation_short = abs(price - sma_short) / sma_short if sma_short > 0 else Decimal("1.0")
            price_deviation_long = abs(price - sma_long) / sma_long if sma_long > 0 else Decimal("1.0")
            
            # Mean reversion threshold: all values within 0.5% of each other
            mean_reversion_threshold = Decimal("0.005")  # 0.5%
            
            # Mean reversion condition: tight clustering around mean
            if (sma_spread < mean_reversion_threshold and 
                price_deviation_short < mean_reversion_threshold and
                price_deviation_long < mean_reversion_threshold):
                regime = "MEAN_REVERSION"
                # Higher confidence for tighter clustering
                # Invert the spread: smaller spread → higher confidence
                tightness = (mean_reversion_threshold - max(sma_spread, price_deviation_short, price_deviation_long))
                confidence = min(Decimal("0.95"), Decimal("0.5") + tightness * Decimal("100.0"))
        
        # --- PRIORITY 3: Trend Detection ---
        # Uptrend condition: short SMA > long SMA AND price > short SMA
        if regime == "UNCERTAIN" and sma_short > sma_long and price > sma_short:
            regime = "TREND_UP"
            confidence = self._calculate_confidence(sma_short, sma_long)
        
        # Downtrend condition: short SMA < long SMA AND price < short SMA
        if regime == "UNCERTAIN" and sma_short < sma_long and price < sma_short:
            regime = "TREND_DOWN"
            confidence = self._calculate_confidence(sma_short, sma_long)
        
        # --- Emit regime detected event ---
        payload = {
            "ts": ts,
            "symbol": symbol,
            "regime": regime,
            "confidence": str(confidence),  # String-encoded Decimal for precision
            "source_model": source_model
        }
        
        self.fsm.emit(
            "EVT:REGIME_DETECTED",
            payload,
            why=f"Regime '{regime}' detected by {source_model} for {symbol}"
        )
        
        self.logger.info(
            f"Detected {regime} for {symbol} by {source_model} "
            f"(confidence: {confidence}, price: {price})"
        )
