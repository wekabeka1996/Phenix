# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""R1 Evaluator: online assessment of bridge impact.

Provides compute_J and evaluate_bridge collecting pre/post windows and emitting
bridge_exec_commit event via provided blackbox emitter.
"""
from __future__ import annotations
import math, time
from dataclasses import dataclass
from typing import Callable, Dict, Any, Optional

@dataclass
class EvalResult:
    bridge_id: str
    dJ: float
    dEFE: float
    dEmp: float
    dHomeo: float
    dP95_trimmed: float
    latency_p95_after: float

def _percentile(arr, p):
    arr = list(arr)
    if not arr:
        return None
    arr.sort()
    p = max(0.0, min(100.0, p))
    k = (len(arr) - 1) * (p / 100.0)
    f = math.floor(k); c = math.ceil(k)
    if f == c:
        return arr[int(k)]
    return arr[f]*(c-k) + arr[c]*(k-f)

def _trimmed_p95(values, alpha=0.05):
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return None
    trim = int(n * alpha)
    core = vals[trim: n - trim] if n > 2*trim else vals
    return _percentile(core, 95)

def compute_J(dEFE, dEmp, dHomeo, penalty_acf=0.0, penalty_spec=0.0, energy_cost=0.0, latency_risk=0.0, w: dict | None=None) -> float:
    w = w or {}
    a = w.get('alpha_dEfe', 1.0)
    b = w.get('beta_dEmp', 0.5)
    g = w.get('gamma_dHomeo', 0.5)
    l1 = w.get('lambda_acf', 0.2)
    l2 = w.get('lambda_spec', 0.2)
    l3 = w.get('lambda_energy', 0.1)
    l4 = w.get('lambda_latency', 0.1)
    return a*dEFE + b*dEmp + g*dHomeo - (l1*penalty_acf + l2*penalty_spec + l3*energy_cost + l4*latency_risk)

def evaluate_bridge(bridge, ctx, cfg: dict, blackbox_emit: Callable[[dict], None], eval_tag: Optional[str] = None) -> EvalResult:
    b_id = getattr(bridge, 'id', 'unknown')
    eval_cfg = ((cfg.get('r1') or {}).get('eval') or {})
    pre_s = float(eval_cfg.get('pre_window_s', 30))
    post_s = float(eval_cfg.get('post_window_s', 60))
    alpha = float(eval_cfg.get('trimmed_alpha', 0.05))
    m = getattr(ctx, 'metrics', None)

    def _mean(x): return sum(x)/len(x) if x else 0.0
    # sample BEFORE
    before = {
        'efe': m.sample_efe(duration_s=pre_s) if m else [],
        'emp': m.sample_empowerment(duration_s=pre_s) if m else [],
        'homeo': m.sample_homeostasis(duration_s=pre_s) if m else [],
        'surprisal': m.sample_surprisal(duration_s=pre_s) if m else [],
        'latency_p95': (m.sample_latency_p95(duration_s=pre_s) if m else 0.0),
    }
    # Allow tests / smoke to skip real waiting
    if not bool(((cfg.get('r1') or {}).get('eval') or {}).get('skip_sleep', False)):
        time.sleep(post_s)
    after = {
        'efe': m.sample_efe(duration_s=post_s) if m else [],
        'emp': m.sample_empowerment(duration_s=post_s) if m else [],
        'homeo': m.sample_homeostasis(duration_s=post_s) if m else [],
        'surprisal': m.sample_surprisal(duration_s=post_s) if m else [],
        'latency_p95': (m.sample_latency_p95(duration_s=post_s) if m else 0.0),
    }
    dEFE = _mean(after['efe']) - _mean(before['efe'])
    dEmp = _mean(after['emp']) - _mean(before['emp'])
    dHomeo = _mean(after['homeo']) - _mean(before['homeo'])
    p95_before = _trimmed_p95(before['surprisal'], alpha)
    p95_after = _trimmed_p95(after['surprisal'], alpha)
    dP95 = (p95_after - p95_before) if (p95_before is not None and p95_after is not None) else 0.0
    lat_after = after['latency_p95'] or 0.0
    J = compute_J(dEFE, dEmp, dHomeo, w=((cfg.get('r1') or {}).get('score_weights') or {}))
    res = EvalResult(b_id, J, dEFE, dEmp, dHomeo, dP95, lat_after)
    payload = {
        'ts': time.time(),
        'event': 'bridge_exec_commit',
        'bridge_id': b_id,
        'dJ': res.dJ,
        'dEFE': res.dEFE,
        'dEmp': res.dEmp,
        'dHomeo': res.dHomeo,
        'dP95_trimmed': res.dP95_trimmed,
        'latency_p95_after': lat_after,
    }
    if eval_tag is not None:
        payload['eval_tag'] = eval_tag
    blackbox_emit(payload)
    return res

__all__ = ["EvalResult", "evaluate_bridge", "compute_J"]
