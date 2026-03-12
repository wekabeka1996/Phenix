"""
Regime Detector Domain - Market Regime Analysis

Analyzes market features to detect current trading regime (TREND_UP, TREND_DOWN, etc.)
Based on logic from legacy aurora/regime/detectors.py

WHY: Enable regime-aware trading decisions [FSMP-PORTING-T01]

REG-FIX-01: BAR-ONLY SSOT
- Only processes FEATURES_CALCULATED events with tf_sec == basis_tf_sec
- Ignores tick-level tf=0 events to prevent double-clocking
- Clock abstraction for deterministic testing
"""

import logging
from collections import deque, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional

from vfoundation.core.protocol import Message
from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import AuroraConfig
from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    extract_canonical_bar_identity,
)
from apps.reference.core.time.clock import Clock, LiveClock
from apps.reference.contracts.runtime_regime_layers import (
    RuntimeRegimeClock,
    RuntimeRegimeLayer,
    RuntimeRegimeScope,
    structural_regime_ref,
)
from apps.reference.telemetry.metrics import inc_data_quality_drop


class RegimeDetector:
    """
    Analyzes market features to detect the current trading regime based on
    pre-configured models.

    Supports multiple detection models (configurable):
    - SMA trend detection (crossover-based)
    - Volatility regime detection (planned)
    - Mean-reversion detection (planned)

    Emits EVT:REGIME_DETECTED events with confidence scores.

    REG-FIX-01: BAR-ONLY mode
    - Only processes events where tf_sec == basis_tf_sec (default: 300 for 5m bars)
    - Clock injection for deterministic testing
    """

    def __init__(
        self,
        config: AuroraConfig,
        fsm,
        *,
        clock: Optional[Clock] = None,
    ):
        """
        Initializes the detector with model configurations.

        Args:
            config: AuroraConfig with regime.yaml fields
            fsm: FSMCore instance for event emission and logging
            clock: Optional Clock for time abstraction (default: LiveClock)
        """
        self.fsm = fsm
        if isinstance(config, dict):
            raise TypeError("RegimeDetector requires AuroraConfig, got dict")
        self.config = config
        self.logger = logging.getLogger(__name__)

        # REG-FIX-01: Clock abstraction (T2B-08 pattern)
        self._clock: Clock = clock or LiveClock()

        # REG-FIX-01: BAR-ONLY SSOT - required fields (fail-closed)
        self._basis_tf_sec: int = config.basis_tf_sec
        self._uncertain_cutoff: float = config.uncertain_cutoff
        self.logger.info(
            f"RegimeDetector: basis_tf_sec={self._basis_tf_sec}, uncertain_cutoff={self._uncertain_cutoff}"
        )

        self._subscribed = False
        self._last_emitted_regime: Dict[str, str] = {}
        self._last_full_ready: Dict[str, bool] = {}

        models_cfg = self.config.models
        if models_cfg is None:
            raise ConfigContractError(
                path="models",
                why="Missing regime models config (expected regime.yaml to populate root models).",
            )

        self.model_config = models_cfg.sma_trend

        self.model_name = "sma_trend_v1"

        self.sma_short_period = int(self.model_config.sma_short_period)
        self.sma_long_period = int(self.model_config.sma_long_period)

        vol_cfg = models_cfg.volatility
        # TASK24.D1: Strict config contract - missing required fields must fail fast.
        for attr in (
            "enabled",
            "atr_period",
            "atr_sma_length",
            "allow_close_to_close_atr",
            "threshold_multiplier",
            "low_vol_multiplier",
            "high_vol_confidence_multiplier",
            "low_vol_confidence_multiplier",
        ):
            try:
                getattr(vol_cfg, attr)
            except AttributeError as e:
                raise ConfigContractError(
                    path=f"models.volatility.{attr}",
                    why=f"Missing required volatility config field: {e}",
                )
        self.atr_period = int(vol_cfg.atr_period)
        self.atr_sma_length = int(vol_cfg.atr_sma_length)
        self._allow_close_to_close_atr = bool(vol_cfg.allow_close_to_close_atr)

        # NOTE: mean_reversion config validated by Pydantic at AuroraConfig level.
        # No explicit checks needed here - missing fields raise ValidationError on config load.

        # Per-symbol rolling buffers for computing SMA/ATR if features don't provide them
        self._price_buf: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max(
                self.sma_short_period, self.sma_long_period))
        )
        self._tr_buf: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self.atr_period))
        self._atr_buf: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self.atr_sma_length))
        self._atr_last: Dict[str, Decimal] = {}
        self._ticks_seen: Dict[str, int] = defaultdict(int)
        self._last_basis_close_boundary_ts_ms: Dict[str, int] = defaultdict(int)

        # HYSTERESIS-SLOPE-GATE-01: State storage
        self._hysteresis_stable: Dict[str, str] = {}  # symbol -> stable_regime
        # symbol -> pending_regime
        self._hysteresis_pending: Dict[str, str] = {}
        self._hysteresis_count: Dict[str, int] = defaultdict(
            int)  # confirm count
        # symbol -> stable confidence
        self._stable_confidence: Dict[str, Decimal] = {}
        self._vol_ratio_buf: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=6))
        self._slope_reject_count: Dict[str, int] = defaultdict(int)

        self.logger.info(
            f"RegimeDetector initialized with model: {self.model_name}")

        self._subscribe_once()

    def _subscribe_once(self) -> None:
        if self._subscribed:
            return
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.handle_event)
        self._subscribed = True
        self.logger.info(
            "RegimeDetector subscribed to EVT:FEATURES_CALCULATED")

    def start(self) -> None:
        self._subscribe_once()

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
            return Decimal(str(self.model_config.confidence_min))

        # Heuristic formula: spread / base * multiplier
        # Multiplier of 20.0 empirically tuned for realistic signals
        confidence_multiplier = Decimal(
            str(self.model_config.confidence_multiplier))

        # For test case: (4050-3900)/3900 = 0.0385 * 20 = 0.77
        spread_ratio = (sma_short - sma_long) / sma_long
        confidence = spread_ratio * confidence_multiplier

        # Bound the confidence between floor (0.5) and ceiling (0.95)
        # Using abs() to handle both uptrend and downtrend signals
        conf_min = Decimal(str(self.model_config.confidence_min))
        conf_max = Decimal(str(self.model_config.confidence_max))

        bounded_confidence = min(
            max(abs(confidence), conf_min), conf_max)
        return bounded_confidence

    @staticmethod
    def _ema(values: list, span: int) -> float:
        """Simple EMA calculation for slope gate."""
        if not values:
            return 0.0
        alpha = 2.0 / (span + 1)
        ema = float(values[0])
        for v in values[1:]:
            ema = alpha * float(v) + (1 - alpha) * ema
        return ema

    def handle_event(self, event: Message) -> None:
        """
        Entry point for handling incoming events.

        REG-FIX-01: BAR-ONLY mode
        - Only processes EVT:FEATURES_CALCULATED with tf_sec == basis_tf_sec
        - Ignores tick-level events (tf_sec=0) to prevent double-clocking

        Args:
            event: Message object with op=EVT, verb=FEATURES_CALCULATED
                   containing feature data in payload

        Emits:
            EVT:REGIME_DETECTED with regime type and confidence score
        """
        if event.verb != "FEATURES_CALCULATED":
            self.logger.debug(f"Ignoring event: {event.verb}")
            return

        pld = event.pld or {}
        symbol = pld.get("symbol")
        ts = pld.get("ts")
        features: Dict[str, Any] = (
            pld.get("features") or {}) if isinstance(pld, dict) else {}

        # REG-FIX-01: BAR-ONLY filter - ignore non-basis timeframes
        tf_sec = pld.get("tf_sec")

        # Silent ignore tick-level events (tf_sec=0) - NOT a data quality issue
        if tf_sec == 0:
            self.logger.debug(
                f"[{symbol}] RegimeDetector: ignoring tick-level features (tf_sec=0)")
            return

        if tf_sec != self._basis_tf_sec:
            self.logger.debug(
                f"[{symbol}] RegimeDetector: ignoring tf_sec={tf_sec} (basis={self._basis_tf_sec})"
            )
            return

        if not symbol or ts is None:
            inc_data_quality_drop(domain="regime_detector",
                                  reason="missing_symbol_or_ts")
            return
        if not isinstance(features, dict) or not features:
            inc_data_quality_drop(domain="regime_detector",
                                  reason="missing_features_dict")
            return

        try:
            ts_ms = int(ts)
        except Exception:
            inc_data_quality_drop(domain="regime_detector", reason="bad_ts")
            return

        bar_identity = extract_canonical_bar_identity(
            pld,
            default_symbol=str(symbol),
            default_timeframe_sec=int(self._basis_tf_sec),
            default_source_mode=RuntimeBarSourceMode.LIVE,
        )
        close_boundary_ts_ms = (
            int(bar_identity.close_boundary_ts_ms)
            if bar_identity is not None
            else int(pld.get("close_boundary_ts_ms") or (ts_ms + 1))
        )
        last_boundary_ts_ms = int(
            self._last_basis_close_boundary_ts_ms.get(symbol, 0) or 0
        )
        if close_boundary_ts_ms > 0 and last_boundary_ts_ms > 0 and close_boundary_ts_ms <= last_boundary_ts_ms:
            self.logger.debug(
                "[%s] RegimeDetector: duplicate basis bar ignored boundary=%s last=%s",
                symbol,
                close_boundary_ts_ms,
                last_boundary_ts_ms,
            )
            return

        self._ticks_seen[symbol] += 1

        # REG-FIX-01: Clock abstraction for deterministic testing
        # Wall-clock for freshness/latency, monotonic for liveness heartbeat.
        now_wall_ms = self._clock.now_ms()
        now_monotonic_ms = int(self._clock.monotonic() * 1000)

        # BAR-TTL-REFORM-02: Use bar_ttl_ms for bar events, tick_ttl_ms for ticks
        # This mirrors the fix in decision_making.py Gate 5
        sys_md = self.config.system.market_data if self.config.system else None
        if tf_sec and tf_sec > 0:
            # Bar event - use lenient bar TTL
            ttl_ms = int(getattr(sys_md, "bar_ttl_ms", 10000)
                         ) if sys_md else 10000
        else:
            # Tick event - use strict tick TTL
            ttl_ms = int(sys_md.tick_ttl_ms) if sys_md else 0

        data_drops: list[str] = []
        data_notes: list[str] = []

        # P0-1 FIX: Check for stale features BEFORE any buffer updates
        is_stale = False
        if ttl_ms > 0 and (now_wall_ms - ts_ms) > ttl_ms:
            data_drops.append("stale_features")
            inc_data_quality_drop(domain="regime_detector",
                                  reason="stale_features")
            is_stale = True

        if "price" not in features:
            inc_data_quality_drop(domain="regime_detector",
                                  reason="missing_price")
            return
        try:
            price = Decimal(str(features["price"]))
        except Exception:
            inc_data_quality_drop(domain="regime_detector", reason="bad_price")
            return
        if price <= 0:
            inc_data_quality_drop(domain="regime_detector", reason="bad_price")
            return

        # P0-1 FIX: Do NOT update buffers with stale data - emit UNCERTAIN and return early
        if is_stale:
            conf_min = Decimal(str(self.model_config.confidence_min))
            warmup = {
                "ticks_seen": int(self._ticks_seen.get(symbol, 0)),
                "full_ready": False,
                "ready": {},
                "reasons": ["drop:stale_features"],
            }
            payload = {
                "ts": ts_ms,
                "ts_ms": ts_ms,
                "symbol": symbol,
                "regime": "UNCERTAIN",
                "confidence": str(conf_min),
                "source_model": "data_quality_gate",
                "regime_layer": RuntimeRegimeLayer.STRUCTURAL.value,
                "regime_scope": RuntimeRegimeScope.PER_SYMBOL.value,
                "regime_clock": RuntimeRegimeClock.BAR.value,
                "regime_owner": "regime_detector",
                "structural_regime_ref": structural_regime_ref(symbol, ts_ms),
                "warmup": warmup,
                "data_quality": {"drops": data_drops, "notes": data_notes},
            }
            self.fsm.emit(
                "EVT:REGIME_DETECTED",
                payload,
                why=f"Regime UNCERTAIN (stale data) for {symbol}",
            )
            self._last_emitted_regime[symbol] = "UNCERTAIN"
            return

        if close_boundary_ts_ms > 0:
            self._last_basis_close_boundary_ts_ms[symbol] = close_boundary_ts_ms

        # Feed price buffer (only with fresh, valid data)
        self._price_buf[symbol].append(price)

        # Compute SMA if not provided (strict: no fallbacks to magic, only buffer-derived)
        sma_short_raw = features.get("sma_short")
        sma_long_raw = features.get("sma_long")
        sma_short = Decimal(
            str(sma_short_raw)) if sma_short_raw is not None else Decimal("0")
        sma_long = Decimal(
            str(sma_long_raw)) if sma_long_raw is not None else Decimal("0")

        sma_short_ready = sma_short > 0
        sma_long_ready = sma_long > 0

        if (not sma_short_ready) and len(self._price_buf[symbol]) >= self.sma_short_period:
            sma_short = sum(list(
                self._price_buf[symbol])[-self.sma_short_period:]) / Decimal(str(self.sma_short_period))
            sma_short_ready = True
        if (not sma_long_ready) and len(self._price_buf[symbol]) >= self.sma_long_period:
            sma_long = sum(list(
                self._price_buf[symbol])[-self.sma_long_period:]) / Decimal(str(self.sma_long_period))
            sma_long_ready = True

        # ATR / volatility pipeline (Wilder). Prefer OHLC TR; close-to-close only with explicit opt-in.
        vol_cfg = self.config.models.volatility  # typed (D1)
        atr_ready = False
        atr_baseline_ready = False
        atr_val: Decimal | None = None
        atr_baseline: Decimal | None = None

        if vol_cfg.enabled and price > 0:
            high_raw = features.get("high")
            low_raw = features.get("low")
            close = price

            prev_close = self._price_buf[symbol][-2] if len(
                self._price_buf[symbol]) >= 2 else None
            tr: Decimal | None = None

            if high_raw is not None and low_raw is not None and prev_close is not None:
                high = Decimal(str(high_raw))
                low = Decimal(str(low_raw))
                if high > 0 and low > 0:
                    tr = max(
                        high - low,
                        abs(high - prev_close),
                        abs(low - prev_close),
                    )
            elif prev_close is not None and self._allow_close_to_close_atr:
                tr = abs(close - prev_close)
                data_notes.append("atr_close_to_close")
            elif prev_close is not None and (not self._allow_close_to_close_atr):
                data_drops.append("atr_missing_ohlc")
                inc_data_quality_drop(
                    domain="regime_detector", reason="atr_missing_ohlc")

            if tr is not None:
                self._tr_buf[symbol].append(tr)

                last_atr = self._atr_last.get(symbol)
                if last_atr is None:
                    if len(self._tr_buf[symbol]) >= self.atr_period:
                        init_atr = sum(
                            list(self._tr_buf[symbol])[-self.atr_period:]) / Decimal(str(self.atr_period))
                        self._atr_last[symbol] = init_atr
                        atr_val = init_atr
                        atr_ready = True
                else:
                    n = Decimal(str(self.atr_period))
                    atr_val = (last_atr * (n - 1) + tr) / n
                    self._atr_last[symbol] = atr_val
                    atr_ready = True

                if atr_ready and atr_val is not None:
                    self._atr_buf[symbol].append(atr_val)
                    if len(self._atr_buf[symbol]) >= self.atr_sma_length:
                        atr_baseline = sum(list(
                            self._atr_buf[symbol])[-self.atr_sma_length:]) / Decimal(str(self.atr_sma_length))
                        atr_baseline_ready = True
                    else:
                        data_notes.append("atr_baseline_insufficient")

        # --- Regime Detection Logic (strict, no magic) ---
        conf_min = Decimal(str(self.model_config.confidence_min))
        conf_max = Decimal(str(self.model_config.confidence_max))

        regime = "UNCERTAIN"
        confidence = conf_min
        source_model = self.model_name

        # Priority 1: Volatility regimes (if enabled and baseline ready)
        if (
            vol_cfg.enabled
            and atr_ready
            and atr_baseline_ready
            and atr_val is not None
            and atr_baseline is not None
            and atr_val > 0
            and atr_baseline > 0
        ):
            threshold_multiplier = Decimal(str(vol_cfg.threshold_multiplier))
            low_vol_multiplier = Decimal(str(vol_cfg.low_vol_multiplier))
            vol_ratio = atr_val / atr_baseline

            if vol_ratio > threshold_multiplier:
                regime = "HIGH_VOLATILITY"
                source_model = "volatility_v2"
                excess = vol_ratio - threshold_multiplier
                conf_mult = Decimal(
                    str(vol_cfg.high_vol_confidence_multiplier))
                confidence = min(conf_max, conf_min + excess * conf_mult)
            elif vol_ratio < low_vol_multiplier:
                regime = "LOW_VOLATILITY"
                source_model = "volatility_v2"
                calm = low_vol_multiplier - vol_ratio
                conf_mult = Decimal(str(vol_cfg.low_vol_confidence_multiplier))
                confidence = min(conf_max, conf_min + calm * conf_mult)

        # HYSTERESIS-SLOPE-GATE-01: Volatility Slope Gate
        storm_rejected = False
        vol_ratio_slope = 0.0
        vol_ratio_val = None

        if atr_baseline_ready and atr_val is not None and atr_baseline is not None and atr_baseline > 0:
            vol_ratio_val = float(atr_val / atr_baseline)
            self._vol_ratio_buf[symbol].append(vol_ratio_val)

            # Slope gate for HIGH_VOLATILITY
            if self.config.vol_slope_gate_enabled and regime == "HIGH_VOLATILITY":
                buf = list(self._vol_ratio_buf[symbol])
                if len(buf) >= 6:
                    ema3 = self._ema(buf, 3)
                    ema6 = self._ema(buf, 6)
                    vol_ratio_slope = ema3 - ema6

                    if vol_ratio_slope <= self.config.vol_slope_gate_eps:
                        self._slope_reject_count[symbol] += 1
                        if self._slope_reject_count[symbol] >= self.config.vol_slope_gate_confirm_bars:
                            data_notes.append(
                                f"slope_gate_reject:slope={vol_ratio_slope:.4f}")
                            self.logger.debug(
                                f"[{symbol}] Slope Gate: HIGH_VOL rejected (dying storm) "
                                f"slope={vol_ratio_slope:.4f} <= eps={self.config.vol_slope_gate_eps}"
                            )
                            regime = "UNCERTAIN"
                            confidence = conf_min
                            source_model = "slope_gate"
                            storm_rejected = True
                    else:
                        self._slope_reject_count[symbol] = 0

        # Lock: if storm_rejected, block TREND_*/MEAN_REVERSION re-classification
        # (This should not happen logically since regime is already UNCERTAIN, but defensive)

        # Priority 2: Mean reversion (requires SMAs)
        mr_cfg = self.config.models.mean_reversion  # typed
        if regime == "UNCERTAIN" and sma_short_ready and sma_long_ready and sma_short > 0 and sma_long > 0 and price > 0:
            threshold = Decimal(str(mr_cfg.threshold))
            sma_spread = abs(sma_short - sma_long) / sma_long
            dev_short = abs(price - sma_short) / sma_short
            dev_long = abs(price - sma_long) / sma_long

            if sma_spread < threshold and dev_short < threshold and dev_long < threshold:
                regime = "MEAN_REVERSION"
                source_model = "mean_reversion_v2"
                tightness = threshold - max(sma_spread, dev_short, dev_long)
                conf_mult = Decimal(str(mr_cfg.confidence_multiplier))
                confidence = min(conf_max, conf_min + tightness * conf_mult)

        # Priority 3: SMA trend
        if regime == "UNCERTAIN" and sma_short_ready and sma_long_ready and sma_short > sma_long and price > sma_short:
            regime = "TREND_UP"
            confidence = self._calculate_confidence(sma_short, sma_long)
        if regime == "UNCERTAIN" and sma_short_ready and sma_long_ready and sma_short < sma_long and price < sma_short:
            regime = "TREND_DOWN"
            confidence = self._calculate_confidence(sma_short, sma_long)

        # HYSTERESIS-SLOPE-GATE-01: Explicit lock - if storm_rejected, block MR/TREND
        if storm_rejected and regime in ("TREND_UP", "TREND_DOWN", "MEAN_REVERSION"):
            data_notes.append(f"slope_gate_lock:blocked_{regime}")
            self.logger.debug(
                f"[{symbol}] Slope Gate Lock: {regime} blocked (storm_rejected=True)"
            )
            regime = "UNCERTAIN"
            confidence = conf_min
            source_model = "slope_gate_lock"

        # TASK24.D5: Data-quality gates are fail-closed (no regime claims on stale/invalid data).
        if data_drops:
            regime = "UNCERTAIN"
            confidence = conf_min
            source_model = "data_quality_gate"

        # REG-FIX-01: uncertain_cutoff - demote low-confidence regimes to UNCERTAIN
        # This prevents weak regime claims from triggering strategy decisions
        if regime != "UNCERTAIN" and float(confidence) < self._uncertain_cutoff:
            data_notes.append(
                f"confidence_below_cutoff:{float(confidence):.3f}<{self._uncertain_cutoff}")
            self.logger.debug(
                f"[{symbol}] Regime {regime} demoted to UNCERTAIN: "
                f"confidence {float(confidence):.3f} < cutoff {self._uncertain_cutoff}"
            )
            regime = "UNCERTAIN"
            confidence = conf_min
            source_model = "uncertain_cutoff_gate"

        warmup_ready_map = {
            "sma_short": bool(sma_short_ready),
            "sma_long": bool(sma_long_ready),
            "atr": bool(atr_ready) if vol_cfg.enabled else True,
            "atr_baseline": bool(atr_baseline_ready) if vol_cfg.enabled else True,
        }
        warmup_reasons: list[str] = []
        if data_drops:
            warmup_reasons.extend([f"drop:{d}" for d in data_drops])
        if data_notes:
            warmup_reasons.extend([f"note:{n}" for n in data_notes])
        if not sma_short_ready:
            warmup_reasons.append("sma_short_insufficient")
        if not sma_long_ready:
            warmup_reasons.append("sma_long_insufficient")
        if vol_cfg.enabled and (not atr_ready):
            warmup_reasons.append("atr_not_ready")
        if vol_cfg.enabled and atr_ready and (not atr_baseline_ready):
            warmup_reasons.append("atr_baseline_not_ready")

        warmup = {
            "ticks_seen": int(self._ticks_seen[symbol] if symbol in self._ticks_seen else 0),
            "full_ready": all(warmup_ready_map.values()) and (not data_drops),
            "ready": warmup_ready_map,
            "reasons": warmup_reasons,
        }

        # DM-CRITICAL-PATCHES-02: Heartbeat emission with changed flag
        # EVT:REGIME_DETECTED is emitted on EVERY basis bar close (heartbeat).
        # 'changed' indicates if regime actually transitioned.

        # HYSTERESIS-SLOPE-GATE-01: Apply hysteresis
        raw_regime = regime
        raw_confidence = confidence
        hysteresis_bars = self.config.hysteresis_bars

        # Initialize hysteresis state if needed
        if symbol not in self._hysteresis_stable:
            self._hysteresis_stable[symbol] = "UNCERTAIN"
            self._hysteresis_pending[symbol] = "UNCERTAIN"
            self._stable_confidence[symbol] = conf_min

        # Update hysteresis counters
        if raw_regime == self._hysteresis_pending[symbol]:
            self._hysteresis_count[symbol] += 1
        else:
            self._hysteresis_pending[symbol] = raw_regime
            self._hysteresis_count[symbol] = 1

        # Transition stable regime if confirmed
        if self._hysteresis_count[symbol] >= hysteresis_bars:
            if self._hysteresis_stable[symbol] != raw_regime:
                self.logger.info(
                    f"[{symbol}] Hysteresis: stable regime transition "
                    f"{self._hysteresis_stable[symbol]} -> {raw_regime} (confirmed {hysteresis_bars} bars)"
                )
            self._hysteresis_stable[symbol] = raw_regime
            self._stable_confidence[symbol] = raw_confidence

        stable_regime = self._hysteresis_stable[symbol]
        stable_confidence = self._stable_confidence[symbol]

        last_regime = self._last_emitted_regime.get(symbol)
        changed = (last_regime is None) or (
            last_regime != stable_regime)  # Use stable_regime

        payload: Dict[str, Any] = {
            "ts": ts_ms,
            "ts_ms": ts_ms,
            "symbol": symbol,
            "regime": stable_regime,  # HYSTERESIS: emit stable_regime
            "confidence": str(stable_confidence),
            "source_model": source_model,
            "regime_layer": RuntimeRegimeLayer.STRUCTURAL.value,
            "regime_scope": RuntimeRegimeScope.PER_SYMBOL.value,
            "regime_clock": RuntimeRegimeClock.BAR.value,
            "regime_owner": "regime_detector",
            "structural_regime_ref": structural_regime_ref(symbol, ts_ms),
            "warmup": warmup,
            "data_quality": {"drops": data_drops, "notes": data_notes},
            # DM-CRITICAL-PATCHES-02: Heartbeat fields
            "changed": changed,
            # Heartbeat timestamp (monotonic)
            "last_update_ts_ms": now_monotonic_ms,
            "calc_lag_ms": now_wall_ms - ts_ms,  # Latency for audit
            # HYSTERESIS-SLOPE-GATE-01: Telemetry metrics
            "raw_regime": raw_regime,
            "raw_confidence": str(raw_confidence),
            "stable_confidence": str(stable_confidence),
            "vol_ratio": str(vol_ratio_val) if vol_ratio_val is not None else None,
            "vol_ratio_slope": vol_ratio_slope if vol_ratio_val is not None else None,
            "storm_rejected": storm_rejected,
            "hysteresis_confirm_count": self._hysteresis_count[symbol],
        }

        why = f"regime={stable_regime} model={source_model} symbol={symbol}"
        if not changed:
            why += " same"
        self.fsm.emit("EVT:REGIME_DETECTED", payload, why=why[:80])

        # Log only on meaningful transitions (avoid hot-path log spam).
        full_ready = bool(warmup.get("full_ready"))
        last_ready = self._last_full_ready.get(symbol)
        if last_ready is not None and (not last_ready) and full_ready:
            self.logger.info(f"[{symbol}] RegimeDetector warmup COMPLETE")
        self._last_full_ready[symbol] = full_ready

        if changed:
            self.logger.info(
                f"[{symbol}] Regime updated: {last_regime or '∅'} → {stable_regime} "
                f"(raw={raw_regime}, confidence={stable_confidence}, model={source_model})"
            )
        self._last_emitted_regime[symbol] = stable_regime

    def feed_warmup_bar(self, symbol: str, bar: Dict[str, Any]) -> None:
        """
        Directly seeds internal regime buffers from a historical bar without
        TTL validation or event emission.

        Used exclusively for startup backfill — bypasses the stale-data gate
        that would reject any bar older than bar_ttl_ms (10 s). Mirrors the
        same fail-safe pattern used by FeatureEngineering._on_htf_bars_imported
        for pillar warmup.

        Args:
            symbol: Trading pair, e.g. "BTCUSDT".
            bar:    Dict with at least {"close": float, "high": float,
                    "low": float}.  "open_ts" is optional (not used for
                    buffer updates, only for logging).
        """
        try:
            close_raw = bar["close"]
            high_raw = bar.get("high")
            low_raw = bar.get("low")
            identity = extract_canonical_bar_identity(
                {
                    "symbol": symbol,
                    "tf_sec": int(self._basis_tf_sec),
                    "bar": bar,
                    "source_mode": RuntimeBarSourceMode.WARMUP_IMPORT.value,
                },
                default_symbol=symbol,
                default_timeframe_sec=int(self._basis_tf_sec),
                default_source_mode=RuntimeBarSourceMode.WARMUP_IMPORT,
            )

            close = Decimal(str(close_raw))
            high = Decimal(str(close_raw if high_raw is None else high_raw))
            low = Decimal(str(close_raw if low_raw is None else low_raw))
        except (InvalidOperation, ValueError, TypeError, KeyError) as exc:
            self.logger.warning(
                "feed_warmup_bar: bad bar for %s: %s", symbol, exc)
            return

        if close <= 0:
            return

        close_boundary_ts_ms = 0
        if identity is not None:
            close_boundary_ts_ms = int(identity.close_boundary_ts_ms)
        else:
            try:
                open_ts_ms = int(bar.get("open_ts") or 0)
            except Exception:
                open_ts_ms = 0
            if open_ts_ms > 0:
                close_boundary_ts_ms = open_ts_ms + int(self._basis_tf_sec) * 1000

        last_boundary_ts_ms = int(
            self._last_basis_close_boundary_ts_ms.get(symbol, 0) or 0
        )
        if close_boundary_ts_ms > 0 and last_boundary_ts_ms > 0 and close_boundary_ts_ms <= last_boundary_ts_ms:
            return

        # ── price buffer ──────────────────────────────────────────────────────
        prev_close: Optional[Decimal] = (
            self._price_buf[symbol][-1] if self._price_buf[symbol] else None
        )
        self._price_buf[symbol].append(close)
        self._ticks_seen[symbol] += 1
        if close_boundary_ts_ms > 0:
            self._last_basis_close_boundary_ts_ms[symbol] = close_boundary_ts_ms

        # ── ATR pipeline (Wilder) ─────────────────────────────────────────────
        vol_cfg = self.config.models.volatility
        if not vol_cfg.enabled:
            return

        tr: Optional[Decimal] = None
        if prev_close is not None and high > 0 and low > 0:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        elif prev_close is not None and self._allow_close_to_close_atr:
            tr = abs(close - prev_close)

        if tr is None:
            return

        self._tr_buf[symbol].append(tr)

        last_atr = self._atr_last.get(symbol)
        if last_atr is None:
            if len(self._tr_buf[symbol]) >= self.atr_period:
                init_atr = (
                    sum(list(self._tr_buf[symbol])[-self.atr_period:])
                    / Decimal(str(self.atr_period))
                )
                self._atr_last[symbol] = init_atr
                self._atr_buf[symbol].append(init_atr)
        else:
            n = Decimal(str(self.atr_period))
            atr_val = (last_atr * (n - 1) + tr) / n
            self._atr_last[symbol] = atr_val
            self._atr_buf[symbol].append(atr_val)
