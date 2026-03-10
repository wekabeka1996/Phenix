"""
SystemStressOverlay domain — Phase 0.5 live runtime integration.

Subscribes to EVT:BAR_CLOSED (tf_sec == basis_tf_sec, default 300 for 5m),
maintains per-symbol rolling stress metrics, runs the A4-configured actuator
FSM, and emits EVT:SYSTEM_STRESS_STATE_UPDATED on state transitions only.

Event contract:
    IN  : EVT:BAR_CLOSED (bar.close, bar.high, bar.low, bar.open, bar.start_ts_ms)
    OUT : EVT:SYSTEM_STRESS_STATE_UPDATED (schema: schemas/system_stress_state_updated_v1.json)

Gating:
    - DM subscribes to OUT, stores state in _system_stress_states[symbol].
    - SafetyGates checks: EXTREME → DENY; STRESS → pass (WARN flag for downstream).

Config SSOT: regime.yaml system_stress section (SystemStressConfig Pydantic model).
Enabled only when config.system_stress.enabled is True.
Burn-in: config.system_stress.burn_in_bars (default 120) bars before first emit.

No-lookahead guarantee: z-score at bar t uses baseline from bars [t-window..t-1].
"""

from __future__ import annotations

import logging
import math
from collections import deque, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

from vfoundation.core.protocol import Message
from apps.reference.config_loader import AuroraConfig


logger = logging.getLogger(__name__)


# ── Incremental (per-bar) actuator FSM ──────────────────────────────────────

class _StressActuator:
    """
    Deterministic per-bar stress actuator FSM replicating actuator_rules.py batch logic.

    States: NORMAL → STRESS → EXTREME (and back).
    Uses hysteresis: consecutive-bar confirmation + min_duration + circuit breaker.
    """

    def __init__(self, sm: Any) -> None:
        """
        Args:
            sm: SystemStressStateMappingConfig (enter/exit thresholds + CB params).
        """
        self.sm = sm
        self.state = "NORMAL"
        self.bars_in_state = 0
        self.pending_desired = "NORMAL"
        self.pending_count = 0
        self._switch_bar_indices: list[int] = []  # bar indices of recent switches
        self.total_switches = 0
        self.circuit_broken = False
        self._bar_index = 0  # increments each step

    def step(self, sl: float) -> Tuple[str, str]:
        """
        Process one stress_level value.

        Returns:
            (state_after_step, why_str)  — state may or may not have changed.
        """
        sm = self.sm
        self._bar_index += 1

        if self.circuit_broken:
            self.bars_in_state += 1
            return self.state, "CB:halt"

        # ── Desired state from current stress_level ──────────────────────
        cur = self.state
        if cur == "NORMAL":
            if sl >= sm.enter_extreme:
                desired = "EXTREME"
            elif sl >= sm.enter_stress:
                desired = "STRESS"
            else:
                desired = "NORMAL"
        elif cur == "STRESS":
            if sl >= sm.enter_extreme:
                desired = "EXTREME"
            elif sl <= sm.exit_stress:
                desired = "NORMAL"
            else:
                desired = "STRESS"
        else:  # EXTREME
            if sl <= sm.exit_extreme:
                desired = "STRESS"
            else:
                desired = "EXTREME"

        # ── No transition wanted ──────────────────────────────────────────
        if desired == cur:
            self.bars_in_state += 1
            self.pending_desired = cur
            self.pending_count = 0
            return self.state, "hold"

        # ── Consecutive confirmation ──────────────────────────────────────
        if desired == self.pending_desired:
            self.pending_count += 1
        else:
            self.pending_desired = desired
            self.pending_count = 1

        # Escalation (risk-on direction) requires enter consecutive bars;
        # de-escalation (risk-off) requires exit consecutive bars.
        is_escalation = (
            (cur == "NORMAL" and desired in ("STRESS", "EXTREME"))
            or (cur == "STRESS" and desired == "EXTREME")
        )
        required = sm.consecutive_bars_enter if is_escalation else sm.consecutive_bars_exit

        # ── Min duration guard ────────────────────────────────────────────
        if self.pending_count < required or self.bars_in_state < sm.min_duration_bars:
            self.bars_in_state += 1
            return self.state, f"pend:{self.pending_count}/{required}"

        # ── Circuit breaker pre-check ─────────────────────────────────────
        cutoff = self._bar_index - sm.switch_window_bars
        self._switch_bar_indices = [b for b in self._switch_bar_indices if b > cutoff]
        if len(self._switch_bar_indices) >= sm.max_switches_per_window:
            self.circuit_broken = True
            self.bars_in_state += 1
            return self.state, "CB:halt"

        # ── Execute transition ────────────────────────────────────────────
        prev_state = self.state
        self.state = desired
        self.bars_in_state = 1  # 1 bar into new state
        self.pending_count = 0
        self.pending_desired = desired
        self._switch_bar_indices.append(self._bar_index)
        self.total_switches += 1
        return self.state, f"{prev_state}->{desired}"


# ── Per-symbol metric rolling state ──────────────────────────────────────────

class _SymbolStressState:
    """
    Per-symbol rolling buffers for incremental z-score computation.

    No-lookahead: at bar t, z-score uses baseline from [t-window..t-1].
    Buffer append happens AFTER z-score computation.
    """

    def __init__(self, window: int, robust_method: str = "none") -> None:
        self.window = window
        self._robust_method = robust_method
        # log_return series (for computing realized_vol including bar t)
        self._logret_deque: deque = deque(maxlen=window)
        # realized_vol baseline (for z_vol; excludes current bar)
        self._vol_baseline: deque = deque(maxlen=window)
        # True Range series (for computing atr including bar t)
        self._tr_deque: deque = deque(maxlen=window)
        # ATR baseline (for z_atr; excludes current bar)
        self._atr_baseline: deque = deque(maxlen=window)
        # Gap baseline (for z_gap; populated after current bar)
        self._gap_baseline: deque = deque(maxlen=window)
        # Bar-range baseline (for z_range; populated after current bar)
        self._range_baseline: deque = deque(maxlen=window)
        # Previous close (needed for gap and log_return)
        self.prev_close: Optional[float] = None
        # Total bars processed
        self.bars_seen: int = 0

    @staticmethod
    def _std(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        return math.sqrt(variance) if variance > 0 else 0.0

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _z(x: float, baseline: deque, clamp: float = 10.0) -> float:
        """Z-score of x against baseline deque (no-lookahead: baseline excludes x)."""
        vals = list(baseline)
        if len(vals) < 2:
            return 0.0
        mean = _SymbolStressState._mean(vals)
        std = _SymbolStressState._std(vals)
        if std < 1e-10:
            return 0.0
        z = (x - mean) / std
        return max(-clamp, min(clamp, z))

    @staticmethod
    def _z_robust(x: float, baseline: deque, method: str, clamp: float = 10.0) -> float:
        """
        Contract:
          - method="none": поточний Gaussian z-score (backward compat) — делегує self._z()
          - method="mad": z_mad = 0.6745 * (x - median(baseline)) / MAD(baseline)
        Invariant: len(baseline) >= 2, else returns 0.0
        Invariant: if MAD < 1e-10 (or std < 1e-10 for "none"): returns 0.0
        """
        if method == "none":
            return _SymbolStressState._z(x, baseline, clamp)
            
        vals = list(baseline)
        if len(vals) < 2:
            return 0.0
            
        vals.sort()
        n = len(vals)
        median = vals[n // 2] if n % 2 == 1 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0
            
        abs_dev = sorted([abs(v - median) for v in vals])
        mad = abs_dev[n // 2] if n % 2 == 1 else (abs_dev[n // 2 - 1] + abs_dev[n // 2]) / 2.0
            
        if mad < 1e-10:
            return 0.0
            
        # MATH_CONST: 0.6745 = 1/Φ⁻¹(3/4), normal MAD scaling.
        z = 0.6745 * (x - median) / mad
        return max(-clamp, min(clamp, z))

    def update(
        self,
        open_: float,
        high: float,
        low: float,
        close: float,
    ) -> Tuple[float, float, float, float, float, float, float, float]:
        """
        Process one bar. Returns (z_atr, z_vol, z_gap, z_range, z_mad_atr, z_mad_vol, z_mad_gap, z_mad_range).

        The z-scores are no-lookahead: baselines contain bars [t-window..t-1].
        """
        self.bars_seen += 1

        # ── 1. Compute raw metrics for bar t ──────────────────────────────

        # Log return (requires prev_close)
        logret = 0.0
        if self.prev_close is not None and self.prev_close > 0:
            try:
                logret = math.log(close / self.prev_close)
            except (ValueError, ZeroDivisionError):
                logret = 0.0

        # True Range: max(H-L, |H-prev_close|, |L-prev_close|)
        if self.prev_close is not None:
            tr = max(
                high - low,
                abs(high - self.prev_close),
                abs(low - self.prev_close),
            )
        else:
            tr = high - low

        # Gap: |open - prev_close| / prev_close
        if self.prev_close is not None and self.prev_close > 0:
            gap = abs(open_ - self.prev_close) / self.prev_close
        else:
            gap = 0.0

        # Bar range: (high - low) / close
        bar_range = (high - low) / close if close > 0 else 0.0

        # ── 2. Compute composite metrics (include bar t) ──────────────────

        # Realized vol: rolling std of log_returns including bar t
        self._logret_deque.append(logret)
        lr_vals = list(self._logret_deque)
        realized_vol = self._std(lr_vals) if len(lr_vals) >= 2 else 0.0

        # ATR: rolling mean of TR including bar t
        self._tr_deque.append(tr)
        tr_vals = list(self._tr_deque)
        atr = self._mean(tr_vals)

        # ── 3. Compute z-scores (no-lookahead: baselines exclude bar t) ──

        z_atr = self._z_robust(atr, self._atr_baseline, method=self._robust_method)
        z_vol = self._z_robust(realized_vol, self._vol_baseline, method=self._robust_method)
        z_gap = self._z_robust(gap, self._gap_baseline, method=self._robust_method)
        z_range = self._z_robust(bar_range, self._range_baseline, method=self._robust_method)

        z_mad_atr = self._z_robust(atr, self._atr_baseline, method="mad")
        z_mad_vol = self._z_robust(realized_vol, self._vol_baseline, method="mad")
        z_mad_gap = self._z_robust(gap, self._gap_baseline, method="mad")
        z_mad_range = self._z_robust(bar_range, self._range_baseline, method="mad")

        # ── 4. Append current metrics to baselines (for next bar) ─────────
        self._atr_baseline.append(atr)
        self._vol_baseline.append(realized_vol)
        self._gap_baseline.append(gap)
        self._range_baseline.append(bar_range)

        self.prev_close = close
        return z_atr, z_vol, z_gap, z_range, z_mad_atr, z_mad_vol, z_mad_gap, z_mad_range


# ── Main domain class ─────────────────────────────────────────────────────────

class SystemStressOverlay:
    """
    Live runtime stress state overlay.

    Subscribes to EVT:BAR_CLOSED, computes composite stress level per symbol
    using no-lookahead z-scores (replicating tools/parquet_pipeline offline logic),
    then runs the A4-configured actuator FSM.

    Emits EVT:SYSTEM_STRESS_STATE_UPDATED only on state transitions.
    If system_stress.enabled is False, this domain is a no-op.
    """

    def __init__(self, config: AuroraConfig, fsm: Any) -> None:
        self.fsm = fsm
        self.logger = logging.getLogger(__name__)

        ss_cfg = getattr(config, "system_stress", None)
        self._enabled: bool = bool(ss_cfg.enabled) if ss_cfg is not None else False
        self._cfg = ss_cfg
        self._basis_tf_sec: int = int(getattr(config, "basis_tf_sec", 300))

        if not self._enabled:
            self.logger.info("SystemStressOverlay: disabled (system_stress.enabled=false)")
            return

        self._window: int = int(ss_cfg.baseline_window)
        self._burn_in: int = int(ss_cfg.burn_in_bars)
        self._sm = ss_cfg.state_mapping
        self._agg = ss_cfg.aggregation
        self._thr = ss_cfg.thresholds
        self._robust_method: str = str(getattr(ss_cfg, "robust_method", "none") or "none")

        # Per-symbol metric state
        self._metric_states: Dict[str, _SymbolStressState] = {}
        # Per-symbol actuator FSM
        self._actuators: Dict[str, _StressActuator] = {}
        # Last emitted state per symbol (for change detection)
        self._last_state: Dict[str, str] = {}

        self._subscribed = False
        self._subscribe_once()

        self.logger.info(
            f"SystemStressOverlay: enabled (window={self._window}, burn_in={self._burn_in}, "
            f"basis_tf_sec={self._basis_tf_sec}, "
            f"method={self._agg.method}, "
            f"enter_stress={self._sm.enter_stress}, CB_window={self._sm.switch_window_bars})"
        )

    def _subscribe_once(self) -> None:
        if self._subscribed:
            return
        self.fsm.listen("EVT:BAR_CLOSED", self.handle_event)
        self._subscribed = True

    # ── Event handling ────────────────────────────────────────────────────

    def handle_event(self, event: Message) -> None:
        """Process EVT:BAR_CLOSED. Filter to basis_tf_sec only."""
        if not self._enabled:
            return

        pld = event.pld or {}
        if not isinstance(pld, dict):
            return

        tf_sec = pld.get("tf_sec")
        if tf_sec != self._basis_tf_sec:
            return

        symbol = pld.get("symbol")
        if not symbol:
            return

        bar = pld.get("bar")
        if not isinstance(bar, dict):
            return

        try:
            close = float(Decimal(str(bar["close"])))
            high = float(Decimal(str(bar["high"])))
            low = float(Decimal(str(bar["low"])))
            open_ = float(Decimal(str(bar["open"])))
            ts_ms = int(bar.get("end_ts_ms") or pld.get("bar_close_ts") or pld.get("ts_ms") or 0)
        except (KeyError, InvalidOperation, ValueError, TypeError) as exc:
            self.logger.debug(f"[{symbol}] SystemStressOverlay: bad bar fields: {exc}")
            return

        if close <= 0 or high <= 0 or low <= 0:
            return

        self._process_bar(symbol, open_, high, low, close, ts_ms)

    def _process_bar(
        self,
        symbol: str,
        open_: float,
        high: float,
        low: float,
        close: float,
        ts_ms: int,
    ) -> None:
        """Process one OHLC bar for a symbol: update metrics, run FSM, emit if changed."""
        # Lazily initialise per-symbol state
        if symbol not in self._metric_states:
            self._metric_states[symbol] = _SymbolStressState(
                window=self._window,
                robust_method=self._robust_method,
            )
            self._actuators[symbol] = _StressActuator(sm=self._sm)
            self._last_state[symbol] = "NORMAL"

        ms = self._metric_states[symbol]
        actuator = self._actuators[symbol]

        # Compute incremental z-scores (no-lookahead)
        z_atr, z_vol, z_gap, z_range, z_mad_atr, z_mad_vol, z_mad_gap, z_mad_range = ms.update(open_=open_, high=high, low=low, close=close)

        # Burn-in: suppress signals until we have enough data
        if ms.bars_seen < self._burn_in:
            return

        # Aggregate z-scores → stress_level [0..1]
        stress_level = self._aggregate(z_atr, z_vol, z_gap, z_range)

        # Step actuator FSM
        prev_state = actuator.state
        new_state, why = actuator.step(stress_level)

        # Emit only on state transition
        if new_state != self._last_state[symbol]:
            self._emit(
                symbol=symbol,
                ts_ms=ts_ms,
                state=new_state,
                prev_state=self._last_state[symbol],
                stress_level=stress_level,
                bars_in_state=actuator.bars_in_state,
                circuit_broken=actuator.circuit_broken,
                bars_seen=ms.bars_seen,
                z_atr=z_atr,
                z_vol=z_vol,
                z_gap=z_gap,
                z_range=z_range,
                z_mad_atr=z_mad_atr,
                z_mad_vol=z_mad_vol,
                z_mad_gap=z_mad_gap,
                z_mad_range=z_mad_range,
                why=why[:80],
            )
            self._last_state[symbol] = new_state

    def _aggregate(self, z_atr: float, z_vol: float, z_gap: float, z_range: float) -> float:
        """Compute composite stress_level [0..1] from z-scores."""
        thr = self._thr
        agg = self._agg

        if agg.method == "weighted_vote":
            weights = agg.weights or {}
            score = 0.0
            if thr.atr_sigma > 0 and z_atr > thr.atr_sigma:
                score += weights.get("atr", 0.0)
            if thr.vol_sigma > 0 and z_vol > thr.vol_sigma:
                score += weights.get("vol", 0.0)
            if thr.gap_sigma > 0 and z_gap > thr.gap_sigma:
                score += weights.get("gap", 0.0)
            if thr.range_sigma > 0 and z_range > thr.range_sigma:
                score += weights.get("range", 0.0)
            return min(1.0, score)

        if agg.method == "k_of_n":
            k = agg.k or 1
            fires = 0
            if thr.atr_sigma > 0 and z_atr > thr.atr_sigma:
                fires += 1
            if thr.vol_sigma > 0 and z_vol > thr.vol_sigma:
                fires += 1
            if thr.gap_sigma > 0 and z_gap > thr.gap_sigma:
                fires += 1
            if thr.range_sigma > 0 and z_range > thr.range_sigma:
                fires += 1
            return min(1.0, fires / k)

        if agg.method == "max":
            ratios = []
            if thr.atr_sigma > 0:
                ratios.append(z_atr / thr.atr_sigma)
            if thr.vol_sigma > 0:
                ratios.append(z_vol / thr.vol_sigma)
            if thr.gap_sigma > 0:
                ratios.append(z_gap / thr.gap_sigma)
            if thr.range_sigma > 0:
                ratios.append(z_range / thr.range_sigma)
            return min(1.0, max(ratios)) if ratios else 0.0

        return 0.0  # unknown method

    def _emit(
        self,
        symbol: str,
        ts_ms: int,
        state: str,
        prev_state: str,
        stress_level: float,
        bars_in_state: int,
        circuit_broken: bool,
        bars_seen: int,
        z_atr: float,
        z_vol: float,
        z_gap: float,
        z_range: float,
        z_mad_atr: float,
        z_mad_vol: float,
        z_mad_gap: float,
        z_mad_range: float,
        why: str,
    ) -> None:
        """Emit EVT:SYSTEM_STRESS_STATE_UPDATED."""
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "ts_ms": ts_ms,
            "state": state,
            "prev_state": prev_state,
            "stress_level": round(stress_level, 4),
            "bars_in_state": bars_in_state,
            "circuit_broken": circuit_broken,
            "bars_seen": bars_seen,
            "z_atr": round(z_atr, 3),
            "z_vol": round(z_vol, 3),
            "z_gap": round(z_gap, 3),
            "z_range": round(z_range, 3),
            "z_mad_atr": round(z_mad_atr, 3),
            "z_mad_vol": round(z_mad_vol, 3),
            "z_mad_gap": round(z_mad_gap, 3),
            "z_mad_range": round(z_mad_range, 3),
            "why": why,
        }
        emit_why = f"stress:{prev_state}->{state} sl={stress_level:.3f} {symbol}"
        self.fsm.emit("EVT:SYSTEM_STRESS_STATE_UPDATED", payload, why=emit_why[:80])
        self.logger.info(
            f"[{symbol}] SystemStress transition: {prev_state} -> {state} "
            f"(sl={stress_level:.3f} bars_in={bars_in_state} CB={circuit_broken}) {why}"
        )
