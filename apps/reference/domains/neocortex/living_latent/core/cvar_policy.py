# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""R2 CVaR policy utilities.

This module provides:
- cvar_estimate(plan_or_series, tau): point estimate of CVaR@tau for a loss series
- cvar_gate(candidate, baseline, tau, min_threshold, enabled=True):
  decide whether candidate is acceptable vs baseline based on CVaR.

Conventions:
- We operate on losses (higher is worse). If only rewards/"J" samples are
  present, we negate them to obtain losses.
- If only a scalar is available, we form a single-element series.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence, Tuple
import math
import warnings


def _as_loss_series(x: Any) -> Sequence[float] | None:
    """Try to extract a sequence of losses from a variety of inputs.

    Supported shapes:
    - Mapping with one of keys: 'losses', 'risks'
    - Mapping with reward-like keys: 'rewards', 'J_samples' -> convert to losses by negation
    - Mapping with scalar 'loss' or 'J'/'reward'
    - Already a sequence (list/tuple) of numbers (assumed losses)
    - Single float/int
    """
    if x is None:
        return None

    # Direct iterable of numbers
    if isinstance(x, (list, tuple)):
        if len(x) == 0:
            return []
        # Ensure numeric
        return [float(v) for v in x]

    # Mapping/dict-like
    if isinstance(x, Mapping):
        # Prefer explicit losses
        for key in ("losses", "risks"):
            if key in x and x[key] is not None:
                seq = x[key]
                if isinstance(seq, (list, tuple)):
                    return [float(v) for v in seq]
        # Reward-like samples -> losses by negation
        for key in ("rewards", "J_samples"):
            if key in x and x[key] is not None:
                seq = x[key]
                if isinstance(seq, (list, tuple)):
                    return [-float(v) for v in seq]
        # Scalar entries
        if "loss" in x and x["loss"] is not None:
            try:
                return [float(x["loss"])]
            except Exception:
                pass
        for key in ("J", "reward"):
            if key in x and x[key] is not None:
                try:
                    return [-float(x[key])]
                except Exception:
                    pass

    # Single numeric
    try:
        return [float(x)]
    except Exception:
        return None


def _quantile(values: Sequence[float], q: float) -> float:
    """Compute empirical quantile with linear interpolation.
    Assumes values is non-empty.
    """
    if not values:
        raise ValueError("quantile() on empty sequence")
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)
    xs = sorted(values)
    n = len(xs)
    # rank-based position (0-indexed between 0 and n-1)
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def _winsorize(values: Sequence[float], p: float = 0.005) -> Sequence[float]:
    if not values:
        return values
    p = max(0.0, min(0.5, float(p)))
    lo_q = _quantile(values, p)
    hi_q = _quantile(values, 1.0 - p)
    return [min(hi_q, max(lo_q, v)) for v in values]


def cvar_estimate(
    plan_or_series: Any,
    tau: float = 0.05,
    exp_weight: float | None = None,
    winsor_p: float = 0.005,
    small_n_smoothing: bool | None = True,
) -> float:
    """Estimate CVaR@tau from a loss series or plan object.

    We treat losses as higher-is-worse. CVaR@tau is the conditional
    expectation in the tail beyond VaR_tau.
    """
    if tau is None:
        tau = 0.05
    series = _as_loss_series(plan_or_series)
    if series is None or len(series) == 0:
        # Fallback: zero-loss baseline if nothing is available
        series = [0.0]
    # Winsorize to reduce extreme tail sensitivity
    series = list(_winsorize(series, winsor_p))
    # Determine VaR threshold
    var_tau = _quantile(series, 1.0 - tau)
    # Optional small-N smoothing: add synthetic points at VaR to stabilize tail
    if small_n_smoothing and len(series) < 20:
        warnings.warn(
            f"CVaR small-N smoothing applied (N={len(series)} < 20) at tau={tau}",
            RuntimeWarning,
            stacklevel=2,
        )
        # Add up to 2 synthetic points at VaR threshold
        synth = 2 if len(series) <= 10 else 1
        series = series + [var_tau] * synth
    # Tail: worst tau fraction (losses >= var_tau)
    tail = [v for v in series if v >= var_tau]
    if not tail:
        tail = [var_tau]
    if exp_weight is None:
        exp_weight = 0.0
    exp_weight = max(0.0, min(0.3, float(exp_weight)))
    if exp_weight == 0.0:
        return float(sum(tail)) / float(len(tail))
    # Exponentially decaying weights (more recent samples matter if series ordered)
    w = []
    n = len(tail)
    alpha = exp_weight
    for i in range(n):
        w.append((1 - alpha) * (alpha ** (n - 1 - i)))
    sw = sum(w) or 1.0
    return float(sum(v * wi for v, wi in zip(tail, w))) / float(sw)


def _relative_gate_threshold(base: float, min_threshold: float) -> float:
    """Compute acceptance threshold against baseline based on min_threshold.

    Interpretation:
    - If min_threshold < 0 (default -0.10), require at least |min_threshold|
      relative improvement: cand <= base * (1 + min_threshold).
      Example: min_threshold=-0.10 -> cand <= 0.9 * base.
    - If min_threshold == 0, strict non-worsening: cand <= base.
    - If min_threshold > 0, allow up to that relative degradation: cand <= base * (1 + min_threshold).
    """
    return base * (1.0 + float(min_threshold))


def cvar_gate(
    candidate: Any,
    baseline: Any,
    tau: float = 0.05,
    min_threshold: float = -0.10,
    enabled: bool = True,
    *,
    exp_weight: float | None = None,
    winsor_p: float = 0.005,
) -> Tuple[bool, dict]:
    """CVaR gate comparing candidate vs baseline.

    Returns (accept, details_dict)
    details contains: {"tau", "cvar_candidate", "cvar_baseline", "threshold", "delta"}
    """
    if not enabled:
        return True, {
            "enabled": False,
            "reason": "disabled",
        }

    if tau is None:
        tau = 0.05
    # clamp params defensively
    if exp_weight is None:
        exp_weight = 0.0
    exp_weight = max(0.0, min(0.3, float(exp_weight)))
    winsor_p = max(0.0, min(0.5, float(winsor_p)))
    cvar_c = cvar_estimate(candidate, tau, exp_weight=exp_weight, winsor_p=winsor_p)
    cvar_b = cvar_estimate(baseline, tau, exp_weight=exp_weight, winsor_p=winsor_p)
    thr = _relative_gate_threshold(cvar_b, min_threshold)
    accept = cvar_c <= thr + 1e-12
    return accept, {
        "enabled": True,
        "tau": float(tau),
        "exp_weight": float(exp_weight),
        "winsor_p": float(winsor_p),
        "cvar_candidate": float(cvar_c),
        "cvar_baseline": float(cvar_b),
        "threshold": float(thr),
        "delta": float(cvar_c - cvar_b),
    }


__all__ = [
    "cvar_estimate",
    "cvar_gate",
]
