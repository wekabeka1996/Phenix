# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""R1-1 SCORE MODULE

SPEC: Controlled Planning R1 — J(T) unified bridge scoring.
Formula (initial):
  J = a*delta_efe + b*delta_emp + c*delta_homeostasis
      - l1*penalty_acf - l2*penalty_spectrum - l3*energy_cost - l4*latency_risk

All deltas and penalties are expected to be pre-normalized to ~[0,1].

Contract:
  get_bridge_score(bridge: dict, ctx: 'R1Context') -> float
    - bridge must include keys for all needed features (missing -> treated as 0).
    - ctx provides weights and fallback normalizers.

Determinism: pure function.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

@dataclass
class ScoreWeights:
    a: float
    b: float
    c: float
    l1: float
    l2: float
    l3: float
    l4: float
    clip_min: float = -10.0
    clip_max: float = 10.0

@dataclass
class R1Context:
    weights: ScoreWeights

FEATURE_MAP = {
    'delta_efe': 0.0,
    'delta_emp': 0.0,
    'delta_homeostasis': 0.0,
    'penalty_acf': 0.0,
    'penalty_spectrum': 0.0,
    'energy_cost': 0.0,
    'latency_risk': 0.0,
}

def get_bridge_score(bridge: Mapping[str, float], ctx: R1Context) -> float:
    w = ctx.weights
    v = {k: float(bridge.get(k, d)) for k, d in FEATURE_MAP.items()}
    raw = (
        w.a * v['delta_efe'] +
        w.b * v['delta_emp'] +
        w.c * v['delta_homeostasis'] -
        w.l1 * v['penalty_acf'] -
        w.l2 * v['penalty_spectrum'] -
        w.l3 * v['energy_cost'] -
        w.l4 * v['latency_risk']
    )
    if raw < w.clip_min: return w.clip_min
    if raw > w.clip_max: return w.clip_max
    return raw
