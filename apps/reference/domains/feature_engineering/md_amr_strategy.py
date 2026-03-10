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
    ) -> None:
        self.channel_window_bars = int(channel_window_bars)
        self.hysteresis_mult = float(hysteresis_mult)
        self.threshold_z = float(threshold_z)
        self.volatility_dampening_factor = float(volatility_dampening_factor)
        self.thr_base = float(thr_base)
        self.alpha = float(alpha)
        self.conf_min = float(conf_min)
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
        conf_ratio = float(score_ctx.get("conf_ratio", 0.0))
        bars_held = int(position_ctx.get("bars_held", 0))
        reached_target = bool(score_ctx.get("reached_channel_target", False))
        expected_edge_after_costs = float(score_ctx.get("expected_edge_after_costs", 0.0))
        fees = float(cost_ctx.get("fee_bps", self.fee_bps)) / 10_000.0
        slippage_buffer = float(cost_ctx.get("slippage_buffer_bps", self.slippage_buffer_bps)) / 10_000.0

        if conf_ratio < self.conf_min:
            return "FULL_CLOSE", "EDGE_GONE_KILLSWITCH"
        if bars_held > self.max_hold_bars:
            return "FULL_CLOSE", "ZOMBIE_POSITION_TIMEOUT"
        
        cost_mult = 2.0 if self.scaleout_cost_model == "round_trip" else 1.0
        if reached_target and expected_edge_after_costs > cost_mult * (fees + slippage_buffer):
            return "PARTIAL_CLOSE", "FEE_AWARE_SCALEOUT"
        return None, None

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
            reached_target = close_now >= avg_close
            expected_edge_after_costs = max(0.0, (avg_high - close_now) / max(abs(close_now), 1e-9))
            exit_side = "SELL"
        else:
            reached_target = close_now <= avg_close
            expected_edge_after_costs = max(0.0, (close_now - avg_low) / max(abs(close_now), 1e-9))
            exit_side = "BUY"

        exit_action, exit_reason = self.resolve_exit_action(
            position_ctx={"bars_held": bars_held, "qty_signed": qty_signed},
            score_ctx={
                "conf_ratio": conf_ratio,
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
