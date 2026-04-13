"""
MD-AMR V1.1 strategy math core.

This module is intentionally isolated from legacy strategy classes.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
import math
from typing import Any, Deque, Dict, Optional

from .indicators import compute_atr, compute_avg_ohlc_channel


def _to_decimal(value: Any) -> Optional[Decimal]:
    try:
        dec = Decimal(str(value))
    except Exception:
        return None
    return dec if dec.is_finite() else None


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class MDAMRSignal:
    intent_kind: str  # ENTRY|FULL_CLOSE|PARTIAL_CLOSE
    side: str
    reason_code: str
    signal_score: float
    conf_ratio: float
    scaleout_fraction: Optional[float]
    price_ref: Decimal
    channel_state: Dict[str, float]
    atr: float
    dir_score: float
    trace: Dict[str, Any]


class MDAMRStrategyV11:
    """Multi-Dimensional Asymmetric Mean Reversion strategy core."""

    def __init__(
        self,
        *,
        channel_window_bars: int,
        hysteresis_mult: float,
        threshold_z: float,
        volatility_dampening_factor: float,
        thr_base: float,
        alpha: float,
        conf_min: float,
        max_hold_bars: int,
        fee_bps: float,
        slippage_buffer_bps: float,
        scaleout_fraction: float,
        weights: Dict[str, float],
        atr_zscore_clamp: float = 10.0,
        atr_std_floor_pct: float = 0.05,
        thr_floor: float = 0.10,
        scaleout_cost_model: str = "round_trip",
        atr_window: int = 14,
        atr_stats_window: int = 64,
        # Package A (Exit Semantics Repair): hold-health threshold.
        # Externalised from hardcode. SSOT: md_amr.yaml -> hold_edge_min.
        hold_edge_min: float = -0.5,
        # Package B (Hold Calibration): tolerance for FEE_AWARE_SCALEOUT target zone.
        # reached_target = close_now >= avg_close * (1 - target_approach_pct)
        # Default 0.002 (0.2%). Set to 0.0 for strict Package-A-baseline semantics.
        target_approach_pct: float = 0.002,
        # Package C.3 (Hold Quality / Soft Decay): expected-progress and penalty shape.
        hold_quality_expected_progress_grace_frac: float = 0.25,
        hold_quality_time_decay_weight: float = 0.35,
        hold_quality_progress_deficit_weight: float = 0.45,
    ) -> None:
        self.channel_window_bars = int(channel_window_bars)
        self.hysteresis_mult = float(hysteresis_mult)
        self.threshold_z = float(threshold_z)
        self.volatility_dampening_factor = float(volatility_dampening_factor)
        self.thr_base = float(thr_base)
        self.alpha = float(alpha)
        # DEPRECATED in exit path (Package A): conf_min is no longer used to
        # trigger EDGE_GONE_KILLSWITCH. Retained for config backward-compatibility.
        # Runtime exit-health threshold is now self.hold_edge_min.
        self.conf_min = float(conf_min)
        self.hold_edge_min = float(hold_edge_min)
        # Package B: target tolerance zone for FEE_AWARE_SCALEOUT.
        self.target_approach_pct = float(target_approach_pct)
        self.hold_quality_expected_progress_grace_frac = float(
            hold_quality_expected_progress_grace_frac)
        self.hold_quality_time_decay_weight = float(
            hold_quality_time_decay_weight)
        self.hold_quality_progress_deficit_weight = float(
            hold_quality_progress_deficit_weight)
        self.max_hold_bars = int(max_hold_bars)
        self.fee_bps = float(fee_bps)
        self.slippage_buffer_bps = float(slippage_buffer_bps)
        self.scaleout_fraction = float(scaleout_fraction)
        self.atr_zscore_clamp = float(atr_zscore_clamp)
        self.atr_std_floor_pct = float(atr_std_floor_pct)
        self.thr_floor = float(thr_floor)
        self.scaleout_cost_model = scaleout_cost_model
        self.weights_raw = {
            "d1": float(weights.get("d1", 0.25)),
            "h1": float(weights.get("h1", 0.25)),
            "m30": float(weights.get("m30", 0.25)),
            "m15": float(weights.get("m15", 0.25)),
        }
        self.atr_window = int(atr_window)
        self.atr_stats_window = int(atr_stats_window)

        max_bars = max(200, self.channel_window_bars + 120)
        self.opens: Deque[Decimal] = deque(maxlen=max_bars)
        self.highs: Deque[Decimal] = deque(maxlen=max_bars)
        self.lows: Deque[Decimal] = deque(maxlen=max_bars)
        self.closes: Deque[Decimal] = deque(maxlen=max_bars)
        self.atr_history: Deque[float] = deque(maxlen=max(atr_stats_window * 2, 256))

    def compute_dir_components_from_900s(self) -> Optional[Dict[str, float]]:
        if len(self.closes) < 96:
            return None

        closes = list(self.closes)
        close_now = float(closes[-1])
        eps = max(close_now * 1e-9, 1e-9)

        def comp(bars: int) -> float:
            if len(closes) <= bars:
                return 0.0
            base = float(closes[-1 - bars])
            ret = (close_now - base) / max(abs(base), eps)
            return _clamp(math.tanh(ret * 6.0), -1.0, 1.0)

        return {
            "d1": comp(96),
            "h1": comp(4),
            "m30": comp(2),
            "m15": comp(1),
        }

    def compute_atr_zscore(self, atr_current: float, atr_ma_n: float, atr_std_n: float) -> float:
        eps = 1e-9
        if not math.isfinite(atr_current) or not math.isfinite(atr_ma_n) or not math.isfinite(atr_std_n):
            return 0.0
        std_floor = max(abs(atr_ma_n) * self.atr_std_floor_pct, eps)
        effective_std = max(atr_std_n, std_floor)
        raw_z = (atr_current - atr_ma_n) / effective_std
        return _clamp(raw_z, -self.atr_zscore_clamp, self.atr_zscore_clamp)

    def apply_dampening_to_weights(self, atr_zscore: float) -> Dict[str, float]:
        w = dict(self.weights_raw)
        if atr_zscore > self.threshold_z:
            w["d1"] = w["d1"] * self.volatility_dampening_factor
            w["h1"] = w["h1"] * self.volatility_dampening_factor

        total = sum(max(0.0, float(v)) for v in w.values())
        if total <= 1e-9:
            return {"d1": 0.25, "h1": 0.25, "m30": 0.25, "m15": 0.25}
        return {k: max(0.0, float(v)) / total for k, v in w.items()}

    def deform_thresholds(self, dir_score: float) -> tuple[float, float, float]:
        bias = float(self.alpha) * abs(float(dir_score))
        if dir_score >= 0:
            thr_buy = self.thr_base - bias
            thr_sell = self.thr_base + bias
        else:
            thr_buy = self.thr_base + bias
            thr_sell = self.thr_base - bias

        thr_buy = _clamp(thr_buy, self.thr_floor, 0.99)
        thr_sell = _clamp(thr_sell, self.thr_floor, 0.99)
        return thr_buy, thr_sell, bias

    def resolve_exit_action(
        self,
        *,
        position_ctx: Dict[str, Any],
        score_ctx: Dict[str, Any],
        cost_ctx: Dict[str, Any],
    ) -> tuple[Optional[str], Optional[str]]:
        # -- Package A (Exit Semantics Repair) --
        # hold_edge captures whether the *positional direction* is still intact.
        # It is computed from dir_score sign vs position sign, NOT from entry-channel
        # geometry. This decouples hold-health from entry-strength so that a price
        # returning toward avg_close does NOT falsely trigger EDGE_GONE_KILLSWITCH.
        #
        # hold_edge = dir_score as seen by this position:
        #   LONG  (+1): positive if dir_score >= 0 (upward structural bias survives)
        #   SHORT (-1): positive if dir_score <= 0 (downward structural bias survives)
        # A value <= hold_edge_min means the structural direction has fully inverted.
        hold_edge: float = float(score_ctx.get("hold_edge", 0.0))
        hold_edge_min: float = float(score_ctx.get("hold_edge_min", -0.5))

        bars_held = int(position_ctx.get("bars_held", 0))
        reached_target = bool(score_ctx.get("reached_channel_target", False))
        expected_edge_after_costs = float(score_ctx.get("expected_edge_after_costs", 0.0))
        fees = float(cost_ctx.get("fee_bps", self.fee_bps)) / 10_000.0
        slippage_buffer = float(cost_ctx.get("slippage_buffer_bps", self.slippage_buffer_bps)) / 10_000.0

        # KILLSWITCH: fire only when positional structural edge is fully gone.
        # Previously used: conf_ratio < conf_min  (entry-geometry based — broken)
        # Now uses: hold_edge <= hold_edge_min    (directional-inversion based)
        if hold_edge <= hold_edge_min:
            return "FULL_CLOSE", "EDGE_GONE_KILLSWITCH"
        if bars_held > self.max_hold_bars:
            return "FULL_CLOSE", "ZOMBIE_POSITION_TIMEOUT"

        cost_mult = 2.0 if self.scaleout_cost_model == "round_trip" else 1.0
        if reached_target and expected_edge_after_costs > cost_mult * (fees + slippage_buffer):
            return "PARTIAL_CLOSE", "FEE_AWARE_SCALEOUT"
        return None, None

    # -------------------------------------------------------------------------
    # Package C.1 (Anchored Target + Progress Tracking) helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _compute_progress_state(progress_pct: float) -> str:
        """Classify progress toward the anchored entry target.

        States:
          NOT_STARTED       progress < 0.0 (price moving against thesis)
          EARLY_PROGRESS    0.0 <= progress < 0.25
          PARTIAL_PROGRESS  0.25 <= progress < 0.70
          NEAR_COMPLETION   0.70 <= progress < 1.0
          COMPLETE          progress >= 1.0

        REVERSING_AGAINST is a sub-class of NOT_STARTED for negative progress.
        """
        if progress_pct < 0.0:
            return "REVERSING_AGAINST"
        if progress_pct < 0.25:
            return "EARLY_PROGRESS"
        if progress_pct < 0.70:
            return "PARTIAL_PROGRESS"
        if progress_pct < 1.0:
            return "NEAR_COMPLETION"
        return "COMPLETE"

    def _compute_progress(
        self,
        *,
        close_now: float,
        entry_price: float,
        entry_target_price: float,
        qty_signed: float,
    ) -> tuple[float, str]:
        """Compute progress_pct and progress_state from anchored references.

        progress_pct = fraction of the original reversion distance completed.
          0.0 = no progress since entry.
          1.0 = full anchored target reached.
          Negative = price moved against thesis.

        Returns (progress_pct, progress_state).
        """
        total_dist = abs(entry_target_price - entry_price)
        if total_dist < 1e-10:
            # Entry price == target: already complete at entry.
            return 1.0, "COMPLETE"
        direction = 1.0 if qty_signed > 0 else -1.0
        moved = direction * (close_now - entry_price)
        progress_pct = moved / total_dist
        return progress_pct, self._compute_progress_state(progress_pct)

    # -------------------------------------------------------------------------
    # Package C.2 (Minimal Setup Quality Score) helpers
    # -------------------------------------------------------------------------

    def _compute_setup_quality(
        self,
        *,
        penetration_depth: float,
        channel_width_pct: float,
        directional_coherence: float,
        atr_zscore: float,
        dir_components: Dict[str, float],
        entry_side: str,
    ) -> Dict[str, Any]:
        """Compute a bounded, explainable setup-quality score at ENTRY time.

        Returns a dict with sub-scores and a composite [0.0, 1.0] score.

        Sub-scores (each [0.0, 1.0]):
          penetration_score:   how far price penetrated beyond channel boundary
          channel_quality:     band width sanity — penalizes degenerate narrow channels
          coherence_score:     how many timeframe components agree with entry direction
          volatility_score:    1.0 when ATR is low, 0.0 when ATR spike is extreme

        Composite: equal-weight mean of the four sub-scores.
        NOTE: This score is observability-only. No exit logic reads it.
        """
        # --- Penetration margin score ---
        # penetration_depth = (avg_low - close) / band for LONG, etc.
        # Ranges 0.0 (barely touching boundary) to typically 0.3+
        # Cap at 0.5 to avoid outlier saturation
        pen_score = _clamp(penetration_depth / 0.5, 0.0, 1.0)

        # --- Channel quality (band sanity) ---
        # channel_width_pct < 0.1% = degenerate, likely noise.
        # Linearly scales to 1.0 at 1.0% band width.
        chan_quality = _clamp(channel_width_pct / 1.0, 0.0, 1.0)

        # --- Directional coherence ---
        # directional_coherence = fraction of TF components agreeing with entry (0.0-1.0)
        # Already in [0.0, 1.0]; use directly.
        coh_score = _clamp(directional_coherence, 0.0, 1.0)

        # --- Volatility context score ---
        # ATR z-score > 2.0 (elevated vol) penalizes. Below -1.0 (very low vol) is good.
        # Maps: atr_zscore <= 0 -> 1.0, atr_zscore >= 3.0 -> 0.0
        vol_score = _clamp(1.0 - (atr_zscore / 3.0), 0.0, 1.0)

        composite = (pen_score + chan_quality + coh_score + vol_score) / 4.0

        return {
            "setup_quality": composite,
            "sq_penetration": pen_score,
            "sq_channel_quality": chan_quality,
            "sq_coherence": coh_score,
            "sq_volatility": vol_score,
        }

    # -------------------------------------------------------------------------
    # Package C.3 (Hold Quality / Soft Decay) helpers
    # -------------------------------------------------------------------------

    def _compute_expected_progress_pct(self, elapsed_hold_frac: float) -> float:
        """Expected anchored progress for the elapsed hold fraction.

        Rule:
          - during the grace window, expected progress = 0.0
          - after grace, expected progress ramps linearly to 1.0 by timeout
        """
        elapsed = _clamp(float(elapsed_hold_frac), 0.0, 1.0)
        grace = _clamp(
            float(self.hold_quality_expected_progress_grace_frac), 0.0, 0.999999)
        if elapsed <= grace:
            return 0.0
        denom = max(1.0 - grace, 1e-9)
        return _clamp((elapsed - grace) / denom, 0.0, 1.0)

    def _compute_hold_quality_overlay(
        self,
        *,
        bars_held: int,
        hold_health: float,
        progress_pct: float,
    ) -> Dict[str, float]:
        """Compute explainable Package C.3 hold-quality overlay fields."""
        elapsed_hold_frac = _clamp(
            max(float(bars_held), 0.0) / max(float(self.max_hold_bars), 1.0),
            0.0,
            1.0,
        )
        remaining_hold_frac = _clamp(1.0 - elapsed_hold_frac, 0.0, 1.0)
        expected_progress_pct = self._compute_expected_progress_pct(
            elapsed_hold_frac)
        actual_progress_pct = _clamp(float(progress_pct), 0.0, 1.0)
        progress_deficit = _clamp(
            expected_progress_pct - actual_progress_pct, 0.0, 1.0)
        time_decay = _clamp(
            (1.0 - remaining_hold_frac) * (1.0 - actual_progress_pct),
            0.0,
            1.0,
        )
        structural_hold_quality = _clamp(
            (float(hold_health) + 1.0) / 2.0, 0.0, 1.0)
        hold_quality_penalty = (
            self.hold_quality_time_decay_weight * time_decay
            + self.hold_quality_progress_deficit_weight * progress_deficit
        )
        hold_quality = _clamp(
            structural_hold_quality - hold_quality_penalty, 0.0, 1.0)
        return {
            "elapsed_hold_frac": elapsed_hold_frac,
            "remaining_hold_frac": remaining_hold_frac,
            "expected_progress_pct": expected_progress_pct,
            "progress_deficit": progress_deficit,
            "time_decay": time_decay,
            "structural_hold_quality": structural_hold_quality,
            "hold_quality_penalty": hold_quality_penalty,
            "hold_quality": hold_quality,
        }

    def on_bar(
        self,
        *,
        bar: Dict[str, Any],
        position_ctx: Dict[str, Any],
        llm_blocked: bool = False,
    ) -> Dict[str, Any]:
        bar_open = _to_decimal(bar.get("open"))
        bar_high = _to_decimal(bar.get("high"))
        bar_low = _to_decimal(bar.get("low"))
        bar_close = _to_decimal(bar.get("close"))
        if not all([bar_open, bar_high, bar_low, bar_close]):
            return {"status": "DEFER", "missing_fields": ["bar.ohlc"]}

        self.opens.append(bar_open)
        self.highs.append(bar_high)
        self.lows.append(bar_low)
        self.closes.append(bar_close)

        channel = compute_avg_ohlc_channel(
            opens=list(self.opens),
            highs=list(self.highs),
            lows=list(self.lows),
            closes=list(self.closes),
            window=self.channel_window_bars,
        )
        if channel is None:
            return {"status": "DEFER", "missing_fields": ["channel_state"]}

        atr_dec = compute_atr(
            highs=list(self.highs),
            lows=list(self.lows),
            closes=list(self.closes),
            window=self.atr_window,
        )
        if atr_dec is None:
            return {"status": "DEFER", "missing_fields": ["atr"]}

        atr_current = float(atr_dec)
        self.atr_history.append(atr_current)
        if len(self.atr_history) < self.atr_stats_window:
            return {"status": "DEFER", "missing_fields": ["atr_stats"]}

        atr_sample = list(self.atr_history)[-self.atr_stats_window:]
        atr_ma = sum(atr_sample) / float(len(atr_sample))
        atr_var = sum((x - atr_ma) ** 2 for x in atr_sample) / float(len(atr_sample))
        atr_std = math.sqrt(max(atr_var, 0.0))
        atr_zscore = self.compute_atr_zscore(atr_current, atr_ma, atr_std)

        dir_components = self.compute_dir_components_from_900s()
        if dir_components is None:
            return {"status": "DEFER", "missing_fields": ["dir_score"]}

        w_norm = self.apply_dampening_to_weights(atr_zscore)
        dir_score = sum(float(dir_components[k]) * float(w_norm[k]) for k in ("d1", "h1", "m30", "m15"))
        dir_score = _clamp(dir_score, -1.0, 1.0)
        thr_buy, thr_sell, bias = self.deform_thresholds(dir_score)

        avg_high = float(channel["avg_high_12"])
        avg_low = float(channel["avg_low_12"])
        avg_close = float(channel["avg_close_12"])
        close_now = float(bar_close)
        band = max(abs(avg_high - avg_low), max(abs(close_now), 1e-9) * 1e-6)
        long_score = max(0.0, (avg_low - close_now) / band) * self.hysteresis_mult
        short_score = max(0.0, (close_now - avg_high) / band) * self.hysteresis_mult
        score = _clamp(long_score - short_score, -1.0, 1.0)

        qty_signed = float(position_ctx.get("qty_signed", 0.0))
        bars_held = int(position_ctx.get("bars_held", 0))
        in_position = abs(qty_signed) > 1e-12

        if qty_signed > 0:
            conf_ratio = _clamp(max(0.0, score) / max(thr_buy, 1e-6), 0.0, 1.0)
        elif qty_signed < 0:
            conf_ratio = _clamp(max(0.0, -score) / max(thr_sell, 1e-6), 0.0, 1.0)
        else:
            conf_ratio = _clamp(max(abs(score), 1e-6) / max(min(thr_buy, thr_sell), 1e-6), 0.0, 1.0)

        qty_base = abs(qty_signed) if in_position else 1.0
        qty_new = qty_base if in_position else max(0.1, conf_ratio)

        trace = {
            "dir_score": dir_score,
            "thr_buy": thr_buy,
            "thr_sell": thr_sell,
            "w_raw": dict(self.weights_raw),
            "w_norm": dict(w_norm),
            "qty_base": qty_base,
            "qty_new": qty_new,
            "conf_ratio": conf_ratio,
            "atr_zscore": atr_zscore,
            "bias": bias,
            "dir_components": dict(dir_components),
        }

        if llm_blocked:
            return {
                "status": "NOOP",
                "reason_code": "LLM_MACRO_BLOCK",
                "trace": trace,
                "dir_score": dir_score,
                "atr": atr_current,
                "channel_state": channel,
            }

        if not in_position:
            if score >= thr_buy:
                # Package C.2: compute setup_quality for entry trace.
                _sq = self._compute_setup_quality(
                    penetration_depth=max(0.0, (avg_low - close_now) / max(band, 1e-9)),
                    channel_width_pct=band / max(abs(close_now), 1e-9) * 100.0,
                    directional_coherence=sum(
                        1 for c in dir_components.values() if c > 0) / 4.0,
                    atr_zscore=atr_zscore,
                    dir_components=dir_components,
                    entry_side="BUY",
                )
                trace.update(_sq)
                return {
                    "status": "SIGNAL",
                    "signal": MDAMRSignal(
                        intent_kind="ENTRY",
                        side="BUY",
                        reason_code="MD_AMR_ENTRY_LONG",
                        signal_score=score,
                        conf_ratio=conf_ratio,
                        scaleout_fraction=None,
                        price_ref=bar_close,
                        channel_state={k: float(v) for k, v in channel.items()},
                        atr=atr_current,
                        dir_score=dir_score,
                        trace=trace,
                    ),
                }
            if score <= -thr_sell:
                # Package C.2: compute setup_quality for entry trace.
                _sq = self._compute_setup_quality(
                    penetration_depth=max(0.0, (close_now - avg_high) / max(band, 1e-9)),
                    channel_width_pct=band / max(abs(close_now), 1e-9) * 100.0,
                    directional_coherence=sum(
                        1 for c in dir_components.values() if c < 0) / 4.0,
                    atr_zscore=atr_zscore,
                    dir_components=dir_components,
                    entry_side="SELL",
                )
                trace.update(_sq)
                return {
                    "status": "SIGNAL",
                    "signal": MDAMRSignal(
                        intent_kind="ENTRY",
                        side="SELL",
                        reason_code="MD_AMR_ENTRY_SHORT",
                        signal_score=score,
                        conf_ratio=conf_ratio,
                        scaleout_fraction=None,
                        price_ref=bar_close,
                        channel_state={k: float(v) for k, v in channel.items()},
                        atr=atr_current,
                        dir_score=dir_score,
                        trace=trace,
                    ),
                }
            return {"status": "NOOP", "trace": trace}

        if qty_signed > 0:
            # Package B: tolerance zone — scaleout triggers when price is within
            # target_approach_pct of avg_close, not only at exact equality.
            reached_target = close_now >= avg_close * (1.0 - self.target_approach_pct)
            expected_edge_after_costs = max(0.0, (avg_high - close_now) / max(abs(close_now), 1e-9))
            exit_side = "SELL"
            # hold_health for LONG: positive when dir_score supports upward structural bias.
            hold_health = _clamp(dir_score, -1.0, 1.0)
        else:
            reached_target = close_now <= avg_close * (1.0 + self.target_approach_pct)
            expected_edge_after_costs = max(0.0, (close_now - avg_low) / max(abs(close_now), 1e-9))
            exit_side = "BUY"
            # hold_health for SHORT: positive when dir_score supports downward structural bias.
            hold_health = _clamp(-dir_score, -1.0, 1.0)

        hold_edge_min = self.hold_edge_min
        # Package B: renamed hold_edge -> hold_health in trace for observability clarity.
        trace["hold_health"] = hold_health
        trace["hold_edge_min"] = hold_edge_min
        # Backward-compat alias for any external consumer still reading hold_edge.
        trace["hold_edge"] = hold_health

        # Package C.1 (Anchored Target + Progress Tracking):
        # Read frozen anchors from position_ctx supplied by handler.
        # Anchors are set at ENTRY and passed back every bar; they never change.
        # If the handler does not yet supply anchors, progress is UNKNOWN (graceful).
        c1_entry_price: Optional[float] = position_ctx.get("entry_price")
        c1_entry_target: Optional[float] = position_ctx.get("entry_target_price")
        trace["elapsed_hold_frac"] = _clamp(
            max(float(bars_held), 0.0) / max(float(self.max_hold_bars), 1.0),
            0.0,
            1.0,
        )
        trace["remaining_hold_frac"] = _clamp(
            1.0 - float(trace["elapsed_hold_frac"]), 0.0, 1.0)
        trace["expected_progress_pct"] = self._compute_expected_progress_pct(
            float(trace["elapsed_hold_frac"]))
        if c1_entry_price is not None and c1_entry_target is not None:
            progress_pct, progress_state = self._compute_progress(
                close_now=close_now,
                entry_price=float(c1_entry_price),
                entry_target_price=float(c1_entry_target),
                qty_signed=qty_signed,
            )
            trace["progress_pct"] = progress_pct
            trace["progress_state"] = progress_state
            trace["entry_price"] = float(c1_entry_price)
            trace["entry_target_price"] = float(c1_entry_target)
            trace.update(
                self._compute_hold_quality_overlay(
                    bars_held=bars_held,
                    hold_health=hold_health,
                    progress_pct=progress_pct,
                )
            )
        else:
            # Anchors not yet available (cold-start or handler not yet wired).
            trace["progress_pct"] = None
            trace["progress_state"] = "UNKNOWN"
            trace["entry_price"] = None
            trace["entry_target_price"] = None
            trace["progress_deficit"] = None
            trace["time_decay"] = None
            trace["structural_hold_quality"] = _clamp(
                (float(hold_health) + 1.0) / 2.0, 0.0, 1.0)
            trace["hold_quality_penalty"] = None
            trace["hold_quality"] = None

        exit_action, exit_reason = self.resolve_exit_action(
            position_ctx={"bars_held": bars_held, "qty_signed": qty_signed},
            score_ctx={
                "hold_edge": hold_health,
                "hold_edge_min": hold_edge_min,
                "reached_channel_target": reached_target,
                "expected_edge_after_costs": expected_edge_after_costs,
            },
            cost_ctx={"fee_bps": self.fee_bps, "slippage_buffer_bps": self.slippage_buffer_bps},
        )
        if exit_action is None:
            return {"status": "NOOP", "trace": trace}

        scaleout_fraction = self.scaleout_fraction if exit_action == "PARTIAL_CLOSE" else None
        if scaleout_fraction is not None:
            trace["qty_new"] = max(0.0, qty_base * float(scaleout_fraction))

        return {
            "status": "SIGNAL",
            "signal": MDAMRSignal(
                intent_kind=exit_action,
                side=exit_side,
                reason_code=str(exit_reason),
                signal_score=score,
                conf_ratio=conf_ratio,
                scaleout_fraction=scaleout_fraction,
                price_ref=bar_close,
                channel_state={k: float(v) for k, v in channel.items()},
                atr=atr_current,
                dir_score=dir_score,
                trace=trace,
            ),
        }
