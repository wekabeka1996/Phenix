"""
Regime Detector Domain - Market Regime Analysis

Analyzes market features to detect current trading regime (TREND_UP, TREND_DOWN, etc.)
Based on logic from legacy aurora/regime/detectors.py

WHY: Enable regime-aware trading decisions [FSMP-PORTING-T01]
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from vfoundation.core.protocol import Message
from apps.reference.config_models import AuroraConfig
from apps.reference.config_regimes import resolve_regime_detector_config


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

    def __init__(self, aurora_cfg: AuroraConfig, fsm):
        """
        Initializes the detector with AuroraConfig for dual-mode resolution.

        Args:
            aurora_cfg: AuroraConfig instance with loaded config
            fsm: FSMCore instance for event emission and logging
        """
        self.fsm = fsm
        self.logger = logging.getLogger(__name__)

        # Use dual-mode resolver instead of direct config parsing
        self.config = resolve_regime_detector_config(aurora_cfg)

        self.logger.info(
            "Resolved regime detector config",
            extra={
                "source": self.config.source,
                "window_minutes": self.config.window_minutes,
                "min_regime_duration_min": self.config.min_regime_duration_min,
                "debounce_changes": self.config.debounce_changes,
            },
        )

        # Keep backward compatibility - expose key fields for existing code
        self.model_name = "sma_trend_v1"

        self.logger.info(
            f"RegimeDetector initialized with typed config: {self.config}")

    def _calculate_confidence(self, sma_short: Decimal, sma_long: Decimal) -> Decimal:
        """
        Calculate confidence score based on SMA spread.

        The formula maps the relative spread between short and long SMAs to a confidence
        score in [confidence_min, confidence_max]. Higher spread indicates stronger trend.

        Args:
            sma_short: Short-term SMA value
            sma_long: Long-term SMA value

        Returns:
            Confidence score as Decimal [confidence_min, confidence_max]
        """
        if sma_long <= 0:
            return Decimal("0.5")

        # Get config values from typed config
        trend_config = self.config.models.get('sma_trend', {})
        confidence_multiplier = Decimal(
            str(trend_config.get('confidence_multiplier', 20.0)))
        confidence_min = Decimal(str(trend_config.get('confidence_min', 0.5)))
        confidence_max = Decimal(str(trend_config.get('confidence_max', 0.95)))

        # Multiplier empirically tuned for realistic signals
        # For test case: (4050-3900)/3900 = 0.0385 * 20 = 0.77
        spread_ratio = abs(sma_short - sma_long) / sma_long
        confidence = spread_ratio * confidence_multiplier

        # Bound the confidence between floor and ceiling
        bounded_confidence = min(
            max(abs(confidence), confidence_min), confidence_max)
        return bounded_confidence

    def _get_unversioned_model_name(self, versioned_model: str) -> str:
        """
        Convert versioned model name to unversioned name as per docs schema.

        Args:
            versioned_model: Versioned model name (e.g., "volatility_v1")

        Returns:
            Unversioned model name (e.g., "volatility")
        """
        # Map versioned names to unversioned enum values from docs
        model_mapping = {
            "sma_trend_v1": "sma_trend",
            "volatility_v1": "volatility",
            "sideways_v1": "sideways"
        }
        return model_mapping.get(versioned_model, versioned_model)

    def _detect_volatility(
        self,
        atr_14: Optional[Decimal],
        atr_14_sma_100: Optional[Decimal]
    ) -> Tuple[str, Decimal, str]:
        """
        Detect HIGH_VOLATILITY or LOW_VOLATILITY regime based on ATR analysis.

        Args:
            atr_14: Current ATR value (14-period)
            atr_14_sma_100: Long-term ATR average (100-period SMA)

        Returns:
            Tuple of (regime, confidence, source_model)
        """
        regime = "UNCERTAIN"
        confidence = Decimal("0.5")
        source_model = self.model_name

        # Get volatility config from typed config
        vol_config = self.config.models.get('volatility', {})

        if (
            vol_config.get('enabled', False)
            and atr_14 is not None
            and atr_14_sma_100 is not None
            and atr_14 > 0
            and atr_14_sma_100 > 0
        ):
            # Get threshold values from typed config
            threshold_multiplier = Decimal(
                str(vol_config.get('threshold_multiplier', 2.0)))
            low_vol_multiplier = Decimal(
                str(vol_config.get('low_vol_multiplier', 0.5)))

            # Get confidence calculation parameters from typed config
            high_vol_base = Decimal(
                str(vol_config.get('high_vol_confidence_base', 0.5)))
            high_vol_multiplier = Decimal(
                str(vol_config.get('high_vol_confidence_multiplier', 2.0)))
            low_vol_base = Decimal(
                str(vol_config.get('low_vol_confidence_base', 0.5)))
            low_vol_multiplier_conf = Decimal(
                str(vol_config.get('low_vol_confidence_multiplier', 3.0)))
            confidence_max = Decimal(
                str(vol_config.get('confidence_max', 0.95)))

            volatility_ratio = atr_14 / atr_14_sma_100

            # HIGH_VOLATILITY: ATR significantly above its long-term average
            if volatility_ratio > threshold_multiplier:
                regime = "HIGH_VOLATILITY"
                source_model = "volatility_v1"

                # Confidence increases with higher volatility ratio
                # Formula: min(confidence_max, base + (ratio - threshold) * multiplier)
                # Example: ratio=2.14, threshold=2.0 → 0.5 + 0.14*2.0 = 0.78
                excess_volatility = volatility_ratio - threshold_multiplier
                confidence = min(
                    confidence_max, high_vol_base +
                    excess_volatility * high_vol_multiplier
                )

            # LOW_VOLATILITY: ATR significantly below its long-term average
            elif volatility_ratio < low_vol_multiplier:
                regime = "LOW_VOLATILITY"
                source_model = "volatility_v1"

                # Confidence increases with lower volatility ratio (market calm)
                # Formula: min(confidence_max, base + (threshold - ratio) * multiplier)
                # Example: ratio=0.43, threshold=0.5 → 0.5 + 0.07*3.0 = 0.71
                calm_factor = low_vol_multiplier - volatility_ratio
                confidence = min(
                    confidence_max, low_vol_base +
                    calm_factor * low_vol_multiplier_conf
                )

        return regime, confidence, source_model

    def _detect_sideways(
        self,
        price: Decimal,
        sma_short: Decimal,
        sma_long: Decimal
    ) -> Tuple[str, Decimal, str]:
        """
        Detect SIDEWAYS regime based on mean reversion analysis.

        Args:
            price: Current price
            sma_short: Short-term SMA
            sma_long: Long-term SMA

        Returns:
            Tuple of (regime, confidence, source_model)
        """
        regime = "UNCERTAIN"
        confidence = Decimal("0.5")
        source_model = self.model_name

        # Calculate relative deviations for mean reversion detection
        # If price and SMAs are tightly clustered → ranging market
        sma_spread = (
            abs(sma_short - sma_long) /
            sma_long if sma_long > 0 else Decimal("1.0")
        )
        price_deviation_short = (
            abs(price - sma_short) /
            sma_short if sma_short > 0 else Decimal("1.0")
        )
        price_deviation_long = (
            abs(price - sma_long) /
            sma_long if sma_long > 0 else Decimal("1.0")
        )

        # Get sideways config from typed config
        sideways_config = self.config.models.get('sideways', {})

        # Get threshold value from typed config
        mean_reversion_threshold = Decimal(
            str(sideways_config.get('deviation_threshold', 0.02)))

        # Get confidence calculation parameters from typed config
        confidence_base = Decimal(
            str(sideways_config.get('confidence_base', 0.5)))
        confidence_multiplier = Decimal(
            str(sideways_config.get('confidence_multiplier', 100.0)))
        confidence_max = Decimal(
            str(sideways_config.get('confidence_max', 0.95)))

        # Mean reversion condition: tight clustering around mean
        if (
            sma_spread < mean_reversion_threshold
            and price_deviation_short < mean_reversion_threshold
            and price_deviation_long < mean_reversion_threshold
        ):
            regime = "SIDEWAYS"
            source_model = "sideways_v1"
            # Higher confidence for tighter clustering
            # Invert the spread: smaller spread → higher confidence
            tightness = mean_reversion_threshold - max(
                sma_spread, price_deviation_short, price_deviation_long
            )
            confidence = min(
                confidence_max, confidence_base +
                tightness * confidence_multiplier
            )

        return regime, confidence, source_model

    def _detect_trend(
        self,
        price: Decimal,
        sma_short: Decimal,
        sma_long: Decimal
    ) -> Tuple[str, Decimal, str]:
        """
        Detect TREND_UP or TREND_DOWN regime based on SMA crossover analysis.

        Args:
            price: Current price
            sma_short: Short-term SMA
            sma_long: Long-term SMA

        Returns:
            Tuple of (regime, confidence, source_model)
        """
        regime = "UNCERTAIN"
        confidence = Decimal("0.5")
        source_model = self.model_name

        # Uptrend condition: short SMA > long SMA AND price > short SMA
        if sma_short > sma_long and price > sma_short:
            regime = "TREND_UP"
            confidence = self._calculate_confidence(sma_short, sma_long)

        # Downtrend condition: short SMA < long SMA AND price < short SMA
        elif sma_short < sma_long and price < sma_short:
            regime = "TREND_DOWN"
            confidence = self._calculate_confidence(sma_short, sma_long)

        return regime, confidence, source_model

    def _safe_decimal_parse(self, value: Any, default: Decimal = Decimal("0"), context: str = "") -> Decimal:
        """
        Safely parse a value to Decimal with error handling.

        Args:
            value: Value to parse (string, number, or other)
            default: Default value if parsing fails
            context: Context string for logging (e.g., "price", "sma_short")

        Returns:
            Decimal value or default if parsing fails
        """
        try:
            if value is None:
                return default
            # Convert to string first to handle various input types
            str_value = str(value).strip()
            if not str_value or str_value.lower() in ('none', 'null', 'nan'):
                return default
            return Decimal(str_value)
        except (ValueError, TypeError, ArithmeticError) as e:
            self.logger.warning(
                f"Failed to parse {context} value '{value}' to Decimal, using default {default}: {e}"
            )
            return default

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

        features: Dict[str, Any] = event.pld.get("features", {}) or {}
        price = self._safe_decimal_parse(
            features.get("price", "0"), Decimal("0"), "price")
        sma_short = self._safe_decimal_parse(features.get(
            "sma_short", "0"), Decimal("0"), "sma_short")
        sma_long = self._safe_decimal_parse(features.get(
            "sma_long", "0"), Decimal("0"), "sma_long")
        symbol = event.pld.get("symbol")
        ts = event.pld.get("ts")

        # Volatility features (optional)
        atr_14 = self._safe_decimal_parse(
            features.get("atr_14"), None, "atr_14"
        ) if "atr_14" in features else None
        atr_14_sma_100 = (
            self._safe_decimal_parse(features.get(
                "atr_14_sma_100"), None, "atr_14_sma_100")
            if "atr_14_sma_100" in features
            else None
        )

        # Validate required base data presence
        if not all([price > 0, symbol, ts]):
            self.logger.debug(
                f"Skipping regime detection for {symbol} - missing price/symbol/ts")
            return

        # --- Regime Detection Logic ---
        regime = "UNCERTAIN"
        confidence = Decimal("0.5")
        source_model = self.model_name

        # --- PRIORITY 1: Volatility Regime Detection ---
        regime, confidence, source_model = self._detect_volatility(
            atr_14, atr_14_sma_100)

        # --- PRIORITY 2: Mean Reversion Detection ---
        if regime == "UNCERTAIN":  # Only check if volatility didn't trigger
            regime, confidence, source_model = self._detect_sideways(
                price, sma_short, sma_long)

        # --- PRIORITY 3: Trend Detection ---
        if regime == "UNCERTAIN":  # Only check if previous models didn't trigger
            regime, confidence, source_model = self._detect_trend(
                price, sma_short, sma_long)

        # --- Emit regime detected event ---
        # Only emit events when regime is actually detected (not UNCERTAIN)
        if regime != "UNCERTAIN":
            payload = {
                "ts": ts,
                "symbol": symbol,
                "regime": regime,
                # Convert confidence to string for event payload per schema
                "confidence": str(confidence),
                # Primary field: model identifier (unversioned as per docs)
                "model": self._get_unversioned_model_name(source_model),
                # Temporary field for backward compatibility (deprecated)
                "source_model": source_model,
            }

            self.fsm.emit(
                "EVT:REGIME_DETECTED",
                payload,
                why=f"Regime '{regime}' detected by {source_model} for {symbol}",
            )

            self.logger.info(
                f"Detected {regime} for {symbol} by {source_model} "
                f"(confidence: {float(confidence):.4f}, price: {price})"
            )
        else:
            self.logger.debug(
                f"No regime detected for {symbol} - all models returned UNCERTAIN"
            )
