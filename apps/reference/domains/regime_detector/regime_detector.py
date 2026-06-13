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
    attach_regime_provenance,
    structural_regime_ref,
)
from apps.reference.telemetry.regime_confidence_audit import (
    emit_regime_bar_close_audit,
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
        self._rd_diag: Dict[str, Dict[str, Any]] = {}

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
        try:
            self.min_trend_spread = Decimal(str(getattr(self.model_config, "min_trend_spread", 0.0)))
        except Exception:
            self.min_trend_spread = Decimal("0.0")

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

        # Phase 3: Adaptive percentile thresholds configuration
        self.vol_adaptive_enabled = False
        self.vol_adaptive_window = 500
        self.vol_adaptive_min_bars = 200
        self.vol_adaptive_high_percentile = 0.90
        self.vol_adaptive_low_percentile = 0.10
        self.vol_adaptive_high_clamp = [1.5, 3.0]
        self.vol_adaptive_low_clamp = [0.3, 0.8]

        adaptive_cfg = getattr(vol_cfg, "adaptive_percentile", None)
        if adaptive_cfg is not None and getattr(adaptive_cfg, "enabled", False):
            self.vol_adaptive_enabled = True
            self.vol_adaptive_window = int(getattr(adaptive_cfg, "window_bars", 500))
            self.vol_adaptive_min_bars = int(getattr(adaptive_cfg, "min_data_bars", 200))
            self.vol_adaptive_high_percentile = float(getattr(adaptive_cfg, "high_vol_percentile", 0.90))
            self.vol_adaptive_low_percentile = float(getattr(adaptive_cfg, "low_vol_percentile", 0.10))
            
            high_clamp = getattr(adaptive_cfg, "high_vol_clamp", [1.5, 3.0])
            self.vol_adaptive_high_clamp = [float(x) for x in high_clamp]
            
            low_clamp = getattr(adaptive_cfg, "low_vol_clamp", [0.3, 0.8])
            self.vol_adaptive_low_clamp = [float(x) for x in low_clamp]

        self._vol_ratio_history = defaultdict(
            lambda: deque(maxlen=self.vol_adaptive_window)
        )

        # Adaptive Mean Reversion configuration
        mr_cfg = models_cfg.mean_reversion
        
        def is_mock(x):
            return type(x).__name__ in ('MagicMock', 'Mock', 'NonCallableMagicMock')

        adaptive_atr_mult = getattr(mr_cfg, "adaptive_atr_multiplier", None)
        if adaptive_atr_mult is not None and not is_mock(adaptive_atr_mult):
            self.mr_adaptive_atr_multiplier = Decimal(str(adaptive_atr_mult))
        else:
            self.mr_adaptive_atr_multiplier = None

        min_thresh = getattr(mr_cfg, "min_threshold", 0.003)
        self.mr_min_threshold = Decimal(str(min_thresh)) if not is_mock(min_thresh) else Decimal("0.003")

        max_thresh = getattr(mr_cfg, "max_threshold", 0.015)
        self.mr_max_threshold = Decimal(str(max_thresh)) if not is_mock(max_thresh) else Decimal("0.015")

        # Adaptive SMA normalization configuration
        sma_norm = getattr(self.model_config, "adaptive_normalization", False)
        self.sma_adaptive_normalization = bool(sma_norm) if not is_mock(sma_norm) else False

        sma_mult = getattr(self.model_config, "normalized_confidence_multiplier", 0.04)
        self.sma_normalized_confidence_multiplier = Decimal(str(sma_mult)) if not is_mock(sma_mult) else Decimal("0.04")

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
        self._last_basis_close_boundary_ts_ms: Dict[str, int] = defaultdict(
            int)

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

    def _diag_for_symbol(self, symbol: str) -> Dict[str, Any]:
        sym = str(symbol)
        if sym not in self._rd_diag:
            self._rd_diag[sym] = {
                "fe_basis_bars_seen": 0,
                "rd_basis_events_received": 0,
                "last_rd_emit_ts_ms": 0,
                "rd_warmup_full_ready": False,
                "rd_warmup_reasons": [],
                "rd_lagging_expected_fe_basis_cadence": False,
                "rd_lag_events": 0,
                "last_basis_close_boundary_ts_ms": 0,
            }
        return self._rd_diag[sym]

    def _update_basis_diag(
        self,
        *,
        symbol: str,
        close_boundary_ts_ms: int,
        warmup: Optional[Dict[str, Any]] = None,
        emit_ts_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        diag = self._diag_for_symbol(symbol)
        diag["fe_basis_bars_seen"] = int(diag["fe_basis_bars_seen"]) + 1
        diag["rd_basis_events_received"] = int(
            diag["rd_basis_events_received"]) + 1

        prev_boundary = int(
            diag.get("last_basis_close_boundary_ts_ms", 0) or 0)
        expected_gap_ms = int(self._basis_tf_sec) * 1000
        lagging = False
        if prev_boundary > 0 and close_boundary_ts_ms > 0:
            actual_gap = int(close_boundary_ts_ms) - prev_boundary
            lag_threshold_ms = max(expected_gap_ms + 1,
                                   int(expected_gap_ms * 1.5))
            if actual_gap > lag_threshold_ms:
                lagging = True
                diag["rd_lag_events"] = int(diag["rd_lag_events"]) + 1

        diag["rd_lagging_expected_fe_basis_cadence"] = bool(lagging)
        if close_boundary_ts_ms > 0:
            diag["last_basis_close_boundary_ts_ms"] = int(close_boundary_ts_ms)
        if emit_ts_ms is not None:
            diag["last_rd_emit_ts_ms"] = int(emit_ts_ms)

        warmup_dict = warmup if isinstance(warmup, dict) else {}
        diag["rd_warmup_full_ready"] = bool(warmup_dict.get("full_ready"))
        reasons = warmup_dict.get("reasons")
        diag["rd_warmup_reasons"] = list(
            reasons) if isinstance(reasons, list) else []
        return diag

    def get_live_blocker_evidence(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Return per-symbol RD basis/warmup diagnostics for live blocker attribution."""
        out: Dict[str, Any] = {}
        for sym, diag in self._rd_diag.items():
            if symbol is not None and str(sym) != str(symbol):
                continue
            out[str(sym)] = {
                "fe_basis_bars_seen": int(diag.get("fe_basis_bars_seen", 0) or 0),
                "rd_basis_events_received": int(diag.get("rd_basis_events_received", 0) or 0),
                "last_rd_emit_ts_ms": int(diag.get("last_rd_emit_ts_ms", 0) or 0),
                "rd_warmup_full_ready": bool(diag.get("rd_warmup_full_ready", False)),
                "rd_warmup_reasons": list(diag.get("rd_warmup_reasons", []) or []),
                "rd_lagging_expected_fe_basis_cadence": bool(
                    diag.get("rd_lagging_expected_fe_basis_cadence", False)
                ),
                "rd_lag_events": int(diag.get("rd_lag_events", 0) or 0),
                "last_basis_close_boundary_ts_ms": int(
                    diag.get("last_basis_close_boundary_ts_ms", 0) or 0
                ),
            }
        return out

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

    def _calculate_confidence_meta(
        self,
        sma_short: Decimal,
        sma_long: Decimal,
        atr_baseline: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
    ) -> tuple[Decimal, bool, bool, Optional[str]]:
        """Return bounded trend confidence plus explicit boundary semantics."""
        conf_min = Decimal(str(self.model_config.confidence_min))
        conf_max = Decimal(str(self.model_config.confidence_max))
        if sma_long == 0:
            return conf_min, False, False, "trend_floor_invalid_base"

        spread_ratio = (sma_short - sma_long) / sma_long
        
        if self.sma_adaptive_normalization and atr_baseline is not None and price is not None and atr_baseline > 0 and price > 0:
            atr_pct = atr_baseline / price
            normalized_spread = spread_ratio / atr_pct
            unbounded = abs(normalized_spread * self.sma_normalized_confidence_multiplier)
        else:
            confidence_multiplier = Decimal(str(self.model_config.confidence_multiplier))
            unbounded = abs(spread_ratio * confidence_multiplier)

        clamped_to_min = unbounded < conf_min
        clamped_to_max = unbounded > conf_max
        bounded_confidence = min(max(unbounded, conf_min), conf_max)
        boundary_reason: Optional[str] = None
        if clamped_to_min:
            boundary_reason = "trend_floor_clamp"
        elif clamped_to_max:
            boundary_reason = "trend_ceiling_clamp"
        return bounded_confidence, clamped_to_min, clamped_to_max, boundary_reason

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

        # P0-1 FIX: Check for stale features BEFORE duplicate guard and buffer updates
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
            self._ticks_seen[symbol] += 1
            conf_min = Decimal(str(self.model_config.confidence_min))
            warmup = {
                "ticks_seen": int(self._ticks_seen.get(symbol, 0)),
                "full_ready": False,
                "ready": {},
                "reasons": ["drop:stale_features"],
            }
            rd_diag = self._update_basis_diag(
                symbol=str(symbol),
                close_boundary_ts_ms=int(close_boundary_ts_ms),
                warmup=warmup,
                emit_ts_ms=int(ts_ms),
            )
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
                "basis_tf_sec": int(self._basis_tf_sec),
                "bar_close_ts_ms": int(close_boundary_ts_ms),
                "warmup": warmup,
                "diagnostics": {
                    "rd": {
                        "fe_basis_bars_seen": int(rd_diag["fe_basis_bars_seen"]),
                        "rd_basis_events_received": int(rd_diag["rd_basis_events_received"]),
                        "last_rd_emit_ts_ms": int(rd_diag["last_rd_emit_ts_ms"]),
                        "rd_warmup_full_ready": bool(rd_diag["rd_warmup_full_ready"]),
                        "rd_warmup_reasons": list(rd_diag["rd_warmup_reasons"]),
                        "rd_lagging_expected_fe_basis_cadence": bool(rd_diag["rd_lagging_expected_fe_basis_cadence"]),
                    }
                },
                "data_quality": {"drops": data_drops, "notes": data_notes},
            }
            payload = attach_regime_provenance(
                payload,
                bar_close_ts_ms=int(close_boundary_ts_ms),
            )
            self.fsm.emit(
                "EVT:REGIME_DETECTED",
                payload,
                why=f"Regime UNCERTAIN (stale data) for {symbol}",
            )
            self._last_emitted_regime[symbol] = "UNCERTAIN"
            return

        # Duplicate boundary guard (only for non-stale events)
        if close_boundary_ts_ms > 0 and last_boundary_ts_ms > 0 and close_boundary_ts_ms <= last_boundary_ts_ms:
            self.logger.debug(
                "[%s] RegimeDetector: duplicate basis bar ignored boundary=%s last=%s",
                symbol,
                close_boundary_ts_ms,
                last_boundary_ts_ms,
            )
            return

        self._ticks_seen[symbol] += 1

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
        pre_cutoff_source_model = source_model
        pre_cutoff_clamped_to_min = False
        pre_cutoff_clamped_to_max = False
        pre_cutoff_boundary_reason: Optional[str] = "default_uncertain_floor"

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
            vol_ratio = atr_val / atr_baseline
            self._vol_ratio_history[symbol].append(float(vol_ratio))

            threshold_multiplier = Decimal(str(vol_cfg.threshold_multiplier))
            low_vol_multiplier = Decimal(str(vol_cfg.low_vol_multiplier))

            if self.vol_adaptive_enabled:
                history = list(self._vol_ratio_history[symbol])
                if len(history) >= self.vol_adaptive_min_bars:
                    sorted_history = sorted(history)
                    n = len(sorted_history)
                    
                    high_idx = int(round(self.vol_adaptive_high_percentile * (n - 1)))
                    high_val = sorted_history[high_idx]
                    
                    low_idx = int(round(self.vol_adaptive_low_percentile * (n - 1)))
                    low_val = sorted_history[low_idx]
                    
                    high_val_clamped = min(max(high_val, self.vol_adaptive_high_clamp[0]), self.vol_adaptive_high_clamp[1])
                    low_val_clamped = min(max(low_val, self.vol_adaptive_low_clamp[0]), self.vol_adaptive_low_clamp[1])
                    
                    threshold_multiplier = Decimal(str(high_val_clamped))
                    low_vol_multiplier = Decimal(str(low_val_clamped))
                    
                    self.logger.debug(
                        f"[{symbol}] Adaptive vol thresholds: high={threshold_multiplier:.4f} (raw={high_val:.4f}), "
                        f"low={low_vol_multiplier:.4f} (raw={low_val:.4f}) over {n} bars"
                    )

            if vol_ratio > threshold_multiplier:
                regime = "HIGH_VOLATILITY"
                source_model = "volatility_v2"
                excess = vol_ratio - threshold_multiplier
                conf_mult = Decimal(
                    str(vol_cfg.high_vol_confidence_multiplier))
                candidate_confidence = conf_min + excess * conf_mult
                pre_cutoff_clamped_to_max = candidate_confidence >= conf_max
                confidence = min(conf_max, candidate_confidence)
                pre_cutoff_boundary_reason = (
                    "volatility_high_ceiling"
                    if pre_cutoff_clamped_to_max
                    else None
                )
            elif vol_ratio < low_vol_multiplier:
                regime = "LOW_VOLATILITY"
                source_model = "volatility_v2"
                calm = low_vol_multiplier - vol_ratio
                conf_mult = Decimal(str(vol_cfg.low_vol_confidence_multiplier))
                candidate_confidence = conf_min + calm * conf_mult
                pre_cutoff_clamped_to_max = candidate_confidence >= conf_max
                confidence = min(conf_max, candidate_confidence)
                pre_cutoff_boundary_reason = (
                    "volatility_low_ceiling"
                    if pre_cutoff_clamped_to_max
                    else None
                )

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
                            pre_cutoff_clamped_to_min = False
                            pre_cutoff_clamped_to_max = False
                            pre_cutoff_boundary_reason = "slope_gate_floor"
                            storm_rejected = True
                    else:
                        self._slope_reject_count[symbol] = 0
            # Slope gate for LOW_VOLATILITY (rising slope/emerging storm)
            elif self.config.vol_slope_gate_enabled and regime == "LOW_VOLATILITY":
                buf = list(self._vol_ratio_buf[symbol])
                if len(buf) >= 6:
                    ema3 = self._ema(buf, 3)
                    ema6 = self._ema(buf, 6)
                    vol_ratio_slope = ema3 - ema6

                    if vol_ratio_slope >= abs(self.config.vol_slope_gate_eps):
                        self._slope_reject_count[symbol] += 1
                        if self._slope_reject_count[symbol] >= self.config.vol_slope_gate_confirm_bars:
                            data_notes.append(
                                f"slope_gate_reject_low:slope={vol_ratio_slope:.4f}")
                            self.logger.debug(
                                f"[{symbol}] Slope Gate: LOW_VOL rejected (emerging storm) "
                                f"slope={vol_ratio_slope:.4f} >= eps={abs(self.config.vol_slope_gate_eps)}"
                            )
                            regime = "UNCERTAIN"
                            confidence = conf_min
                            source_model = "slope_gate"
                            pre_cutoff_clamped_to_min = False
                            pre_cutoff_clamped_to_max = False
                            pre_cutoff_boundary_reason = "slope_gate_floor"
                            storm_rejected = True
                    else:
                        self._slope_reject_count[symbol] = 0

        # Lock: if storm_rejected, block TREND_*/MEAN_REVERSION re-classification
        # (This should not happen logically since regime is already UNCERTAIN, but defensive)

        # Priority 2: Mean reversion (requires SMAs)
        mr_cfg = self.config.models.mean_reversion  # typed
        if regime == "UNCERTAIN" and sma_short_ready and sma_long_ready and sma_short > 0 and sma_long > 0 and price > 0:
            threshold = Decimal(str(mr_cfg.threshold))
            if self.mr_adaptive_atr_multiplier is not None and atr_ready and atr_val is not None:
                atr_pct = atr_val / price
                adaptive_threshold = atr_pct * self.mr_adaptive_atr_multiplier
                threshold = min(max(adaptive_threshold, self.mr_min_threshold), self.mr_max_threshold)

            sma_spread = abs(sma_short - sma_long) / sma_long
            dev_short = abs(price - sma_short) / sma_short
            dev_long = abs(price - sma_long) / sma_long

            if sma_spread < threshold and dev_short < threshold and dev_long < threshold:
                regime = "MEAN_REVERSION"
                source_model = "mean_reversion_v2"
                tightness = threshold - max(sma_spread, dev_short, dev_long)
                conf_mult = Decimal(str(mr_cfg.confidence_multiplier))
                candidate_confidence = conf_min + tightness * conf_mult
                pre_cutoff_clamped_to_max = candidate_confidence >= conf_max
                confidence = min(conf_max, candidate_confidence)
                pre_cutoff_boundary_reason = (
                    "mean_reversion_ceiling"
                    if pre_cutoff_clamped_to_max
                    else None
                )

        # Priority 3: SMA trend
        if regime == "UNCERTAIN" and sma_short_ready and sma_long_ready and price > 0:
            sma_spread = abs(sma_short - sma_long) / sma_long
            if sma_spread >= self.min_trend_spread:
                if sma_short > sma_long and price > sma_long:
                    regime = "TREND_UP"
                    (
                        confidence,
                        pre_cutoff_clamped_to_min,
                        pre_cutoff_clamped_to_max,
                        pre_cutoff_boundary_reason,
                    ) = self._calculate_confidence_meta(
                        sma_short, 
                        sma_long, 
                        atr_baseline=atr_baseline, 
                        price=price
                    )
                elif sma_short < sma_long and price < sma_long:
                    regime = "TREND_DOWN"
                    (
                        confidence,
                        pre_cutoff_clamped_to_min,
                        pre_cutoff_clamped_to_max,
                        pre_cutoff_boundary_reason,
                    ) = self._calculate_confidence_meta(
                        sma_short, 
                        sma_long, 
                        atr_baseline=atr_baseline, 
                        price=price
                    )

        # HYSTERESIS-SLOPE-GATE-01: Explicit lock - if storm_rejected, block MR/TREND
        if storm_rejected and regime in ("TREND_UP", "TREND_DOWN", "MEAN_REVERSION"):
            data_notes.append(f"slope_gate_lock:blocked_{regime}")
            self.logger.debug(
                f"[{symbol}] Slope Gate Lock: {regime} blocked (storm_rejected=True)"
            )
            regime = "UNCERTAIN"
            confidence = conf_min
            source_model = "slope_gate_lock"
            pre_cutoff_clamped_to_min = False
            pre_cutoff_clamped_to_max = False
            pre_cutoff_boundary_reason = "slope_gate_lock_floor"

        # TASK24.D5: Data-quality gates are fail-closed (no regime claims on stale/invalid data).
        if data_drops:
            regime = "UNCERTAIN"
            confidence = conf_min
            source_model = "data_quality_gate"
            pre_cutoff_clamped_to_min = False
            pre_cutoff_clamped_to_max = False
            pre_cutoff_boundary_reason = "data_quality_floor"

        pre_cutoff_regime = regime
        pre_cutoff_confidence = confidence
        pre_cutoff_source_model = source_model
        demoted_to_uncertain = False
        raw_boundary_reason = pre_cutoff_boundary_reason

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
            demoted_to_uncertain = True
            raw_boundary_reason = "uncertain_cutoff_floor"

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
        carried_previous_stable = bool(
            self._hysteresis_count[symbol] < hysteresis_bars
            and (
                stable_regime != raw_regime
                or stable_confidence != raw_confidence
            )
        )

        last_regime = self._last_emitted_regime.get(symbol)
        changed = (last_regime is None) or (
            last_regime != stable_regime)  # Use stable_regime
        emitted_confidence_kind = (
            "hysteresis_carried"
            if carried_previous_stable
            else "stable_from_uncertain_cutoff"
            if demoted_to_uncertain
            else "stable_transition_confirmed"
            if changed
            else "stable_heartbeat"
        )
        reason_parts = [
            f"pre_cutoff_source={pre_cutoff_source_model}",
            f"pre_cutoff={pre_cutoff_regime}:{float(pre_cutoff_confidence):.6f}",
        ]
        if pre_cutoff_boundary_reason:
            reason_parts.append(pre_cutoff_boundary_reason)
        if demoted_to_uncertain:
            reason_parts.append(
                f"uncertain_cutoff:{float(pre_cutoff_confidence):.6f}<{self._uncertain_cutoff:.6f}"
            )
        if carried_previous_stable:
            reason_parts.append(
                f"hysteresis_carry={stable_regime}:{float(stable_confidence):.6f}"
            )
        else:
            reason_parts.append(
                f"hysteresis_confirm={self._hysteresis_count[symbol]}/{hysteresis_bars}"
            )
        if data_drops:
            reason_parts.append("drops=" + ",".join(data_drops))
        if data_notes:
            reason_parts.append("notes=" + ",".join(data_notes))
        reason_summary = "; ".join(reason_parts)

        payload: Dict[str, Any] = {
            "ts": ts_ms,
            "ts_ms": ts_ms,
            "symbol": symbol,
            "regime": stable_regime,  # HYSTERESIS: emit stable_regime
            "confidence": str(stable_confidence),
            "source_model": source_model,
            "pre_cutoff_source_model": pre_cutoff_source_model,
            "regime_layer": RuntimeRegimeLayer.STRUCTURAL.value,
            "regime_scope": RuntimeRegimeScope.PER_SYMBOL.value,
            "regime_clock": RuntimeRegimeClock.BAR.value,
            "regime_owner": "regime_detector",
            "structural_regime_ref": structural_regime_ref(symbol, ts_ms),
            "basis_tf_sec": int(self._basis_tf_sec),
            "bar_close_ts_ms": int(close_boundary_ts_ms),
            "warmup": warmup,
            "data_quality": {"drops": data_drops, "notes": data_notes},
            # DM-CRITICAL-PATCHES-02: Heartbeat fields
            "changed": changed,
            # Heartbeat timestamp (monotonic)
            "last_update_ts_ms": now_monotonic_ms,
            "calc_lag_ms": now_wall_ms - ts_ms,  # Latency for audit
            # HYSTERESIS-SLOPE-GATE-01: Telemetry metrics
            "confidence_min": str(conf_min),
            "confidence_max": str(conf_max),
            "pre_cutoff_regime": pre_cutoff_regime,
            "pre_cutoff_confidence": str(pre_cutoff_confidence),
            "pre_cutoff_clamped_to_min": pre_cutoff_clamped_to_min,
            "pre_cutoff_clamped_to_max": pre_cutoff_clamped_to_max,
            "pre_cutoff_boundary_reason": pre_cutoff_boundary_reason,
            "uncertain_cutoff": float(self._uncertain_cutoff),
            "demoted_to_uncertain": demoted_to_uncertain,
            "raw_regime": raw_regime,
            "raw_confidence": str(raw_confidence),
            "raw_boundary_reason": raw_boundary_reason,
            "stable_confidence": str(stable_confidence),
            "vol_ratio": str(vol_ratio_val) if vol_ratio_val is not None else None,
            "vol_ratio_slope": vol_ratio_slope if vol_ratio_val is not None else None,
            "storm_rejected": storm_rejected,
            "hysteresis_bars": hysteresis_bars,
            "hysteresis_confirm_count": self._hysteresis_count[symbol],
            "carried_previous_stable": carried_previous_stable,
            "emitted_confidence_kind": emitted_confidence_kind,
            "reason_summary": reason_summary,
        }
        payload = attach_regime_provenance(
            payload,
            bar_close_ts_ms=int(close_boundary_ts_ms),
        )
        rd_diag = self._update_basis_diag(
            symbol=str(symbol),
            close_boundary_ts_ms=int(close_boundary_ts_ms),
            warmup=warmup,
            emit_ts_ms=int(ts_ms),
        )
        payload["diagnostics"] = {
            "rd": {
                "fe_basis_bars_seen": int(rd_diag["fe_basis_bars_seen"]),
                "rd_basis_events_received": int(rd_diag["rd_basis_events_received"]),
                "last_rd_emit_ts_ms": int(rd_diag["last_rd_emit_ts_ms"]),
                "rd_warmup_full_ready": bool(rd_diag["rd_warmup_full_ready"]),
                "rd_warmup_reasons": list(rd_diag["rd_warmup_reasons"]),
                "rd_lagging_expected_fe_basis_cadence": bool(rd_diag["rd_lagging_expected_fe_basis_cadence"]),
                "rd_lag_events": int(rd_diag["rd_lag_events"]),
            }
        }
        try:
            emit_regime_bar_close_audit(
                logger=self.logger,
                symbol=str(symbol),
                ts_ms=int(ts_ms),
                basis_tf_sec=int(self._basis_tf_sec),
                bar_close_ts_ms=int(close_boundary_ts_ms),
                structural_regime_ref=payload["structural_regime_ref"],
                changed=changed,
                regime=stable_regime,
                raw_regime=raw_regime,
                source_model=source_model,
                pre_cutoff_source_model=pre_cutoff_source_model,
                confidence_min=float(conf_min),
                confidence_max=float(conf_max),
                pre_cutoff_regime=pre_cutoff_regime,
                pre_cutoff_confidence=float(pre_cutoff_confidence),
                raw_confidence=float(raw_confidence),
                stable_confidence=float(stable_confidence),
                emitted_confidence=float(stable_confidence),
                pre_cutoff_clamped_to_min=pre_cutoff_clamped_to_min,
                pre_cutoff_clamped_to_max=pre_cutoff_clamped_to_max,
                pre_cutoff_boundary_reason=pre_cutoff_boundary_reason,
                raw_boundary_reason=raw_boundary_reason,
                uncertain_cutoff=float(self._uncertain_cutoff),
                demoted_to_uncertain=demoted_to_uncertain,
                hysteresis_bars=hysteresis_bars,
                hysteresis_confirm_count=int(self._hysteresis_count[symbol]),
                carried_previous_stable=carried_previous_stable,
                emitted_confidence_kind=emitted_confidence_kind,
                reason_summary=reason_summary,
                warmup_full_ready=bool(warmup.get("full_ready")),
                data_quality_drops=list(data_drops),
                data_quality_notes=list(data_notes),
            )
        except Exception:
            self.logger.warning(
                "[%s] REGIME_AUDIT bar_close emit failed",
                symbol,
                exc_info=True,
            )

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
                close_boundary_ts_ms = open_ts_ms + \
                    int(self._basis_tf_sec) * 1000

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
