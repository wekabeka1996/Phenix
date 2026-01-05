# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""TVF2 (Transfer Validation Framework 2.0) utilities.

SPEC: docs/Road_map.md (AUR-TVF-801) placeholder implementation.

Provides lightweight primitives:
 - compute_dcts: domain-conditional transfer score (simplified surrogate)
 - delta_invariants: compare invariant metrics between control and treatment bridge sets
 - quantile_grid: compute selected quantiles for a numeric sequence

This is an R0-lite scaffold; real implementation will plug into replay &
bridge evaluation artifacts once heavier metrics (ξ, θ_e, λ_U) are defined.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence, Dict, Any, Iterable, Tuple
import math

@dataclass
class DCTSResult:
    dcts: float
    support: int
    domain_balance: float
    details: Dict[str, Any]


def quantile_grid(values: Sequence[float], qs: Sequence[float] = (0.1,0.25,0.5,0.75,0.9,0.95)) -> Dict[str,float]:
    arr = [float(v) for v in values if isinstance(v,(int,float)) and math.isfinite(v)]
    if not arr:
        return {f"q{int(q*100)}": float('nan') for q in qs}
    arr.sort()
    out: Dict[str,float] = {}
    n = len(arr)
    for q in qs:
        if n == 1:
            val = arr[0]
        else:
            k = (n-1)*q
            f = math.floor(k); c = math.ceil(k)
            if f == c:
                val = arr[int(k)]
            else:
                val = arr[f]*(c-k) + arr[c]*(k-f)
        out[f"q{int(q*100)}"] = float(val)
    return out


def compute_dcts(domain_a: Sequence[float], domain_b: Sequence[float]) -> DCTSResult:
    """Compute a very lightweight proxy for domain-conditional transfer score.

    Intuition (placeholder): higher overlap + similar central tendency => higher score.
    We approximate by inverse normalized Wasserstein-1 (L1 between sorted lists) scaled to [0,1].
    """
    a = [float(x) for x in domain_a if isinstance(x,(int,float)) and math.isfinite(x)]
    b = [float(x) for x in domain_b if isinstance(x,(int,float)) and math.isfinite(x)]
    if not a or not b:
        return DCTSResult(dcts=0.0, support=0, domain_balance=0.0, details={"reason":"empty_domain"})
    a.sort(); b.sort()
    # pad shorter by edge replication for simple alignment
    n = max(len(a), len(b))
    def _stretch(seq, n):
        if len(seq) == n:
            return seq
        if len(seq) == 1:
            return seq * n
        out = []
        for i in range(n):
            idx = int(i*(len(seq)-1)/(n-1))
            out.append(seq[idx])
        return out
    aa = _stretch(a, n); bb = _stretch(b, n)
    l1 = sum(abs(x-y) for x,y in zip(aa,bb))/n
    # normalize by pooled span
    span = max(max(aa)-min(aa), max(bb)-min(bb), 1e-9)
    dist_norm = min(1.0, l1/span)
    score = 1.0 - dist_norm
    balance = min(len(a),len(b)) / max(len(a),len(b))
    return DCTSResult(dcts=score*balance, support=n, domain_balance=balance, details={"l1_norm":l1, "span":span})


def delta_invariants(base: Sequence[float], test: Sequence[float]) -> Dict[str, Any]:
    """Compute simple delta invariants between two numeric samples.

    Returns keys representing magnitude & direction of shift (mean, median, q90, support).
    Future extension will incorporate ξ, θ_e, λ_U invariants from spec.
    """
    b = [float(x) for x in base if isinstance(x,(int,float)) and math.isfinite(x)]
    t = [float(x) for x in test if isinstance(x,(int,float)) and math.isfinite(x)]
    if not b or not t:
        return {"support":0, "mean_delta": float('nan'), "median_delta": float('nan'), "q90_delta": float('nan')}
    def _mean(xs): return sum(xs)/len(xs) if xs else float('nan')
    import statistics as _st
    def _median(xs):
        try:
            return float(_st.median(xs))
        except Exception:
            xs2 = sorted(xs); return xs2[len(xs2)//2]
    def _percentile(xs, p):
        xs = sorted(xs); n=len(xs)
        if n==1: return xs[0]
        k=(n-1)*p; f=math.floor(k); c=math.ceil(k)
        if f==c: return xs[int(k)]
        return xs[f]*(c-k) + xs[c]*(k-f)
    return {
        "support": min(len(b), len(t)),
        "mean_delta": _mean(t) - _mean(b),
        "median_delta": _median(t) - _median(b),
        "q90_delta": _percentile(t,0.9) - _percentile(b,0.9),
    }

__all__ = ["compute_dcts", "delta_invariants", "quantile_grid", "DCTSResult"]
