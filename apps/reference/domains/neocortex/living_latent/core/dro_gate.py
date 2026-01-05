"""DRO Gate & OT Sinkhorn deterministic stub (R2 Hybrid)

Provides:
  - OTSinkhornStub: lightweight, deterministic stand‑in for OT/Sinkhorn distance.
  - DROGate: probabilistic rejection gate using logistic rho(H) where H is a
             hazard proxy blended from selected runtime metrics and OT stub cost.

Design Goals:
  - Zero external deps (pure numpy / stdlib)
  - Deterministic for identical inputs (seed derived from stable tuple)
  - Fail‑open: on any exception evaluate() returns allow=True with reason="error".

Configuration (expected in r2.yaml under r2.hybrid.dro_gate):
  enabled: bool
  k: float                # logistic slope (default 6.0)
  mid: float              # logistic midpoint H0 (default 0.5)
  hazard_source: str      # one of efe, empowerment, random (default efe)
  blend_sinkhorn: float   # weight in [0,1] for blending sinkhorn cost into H (default 0.5)
  enable_min_72h: int     # activate only if last_72h acceptance >= this (if provided externally)

Usage:
  gate = DROGate(cfg_dict, acceptance_metrics={'last_72h': 42})
  decision = gate.evaluate(efe=1.2, empowerment=0.8)
  if not decision['allow']:
      # block / replace action

Hazard Computation:
  Base metric M chosen by hazard_source.
  M is normalized to (0,1) via M/(M+scale) with scale=10.0.
  Sinkhorn cost C in [0, +inf) -> c_norm = C/(C+1).
  H = (1-blend)*M + blend*c_norm.
  rho(H) = 1/(1 + exp(-k*(H - mid))).
  Block with probability rho(H) (i.e. higher hazard => more likely to block).

Logging fields returned by evaluate():
  {
    'allow': bool,
    'hazard': float,
    'rho': float,
    'blocked_prob': float,   # == rho
    'u': float,              # sampled uniform
    'reason': str | None,
    'enabled': bool,
  }
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Dict, Any, Sequence

import numpy as np


@dataclass(slots=True)
class OTSinkhornStub:
    """Deterministic lightweight surrogate for OT/Sinkhorn distance.

    We emulate a transport cost between two 1D or small vectors by:
      1. Normalizing inputs to probability distributions (L1).
      2. Returning L1 distance (which upper-bounds 2-Wasserstein for discrete support).
    This keeps semantics monotonic while avoiding heavy iterations.
    """
    epsilon: float = 0.1  # kept for interface semantic compatibility

    def distance(self, p: Sequence[float], q: Sequence[float]) -> float:
        try:
            p_arr = np.asarray(p, dtype=float).flatten()
            q_arr = np.asarray(q, dtype=float).flatten()
            if p_arr.size == 0 or q_arr.size == 0:
                return 0.0
            # Pad shorter
            if p_arr.size < q_arr.size:
                p_arr = np.pad(p_arr, (0, q_arr.size - p_arr.size))
            elif q_arr.size < p_arr.size:
                q_arr = np.pad(q_arr, (0, p_arr.size - q_arr.size))
            # Shift & relu to avoid negatives then normalize
            def _norm(x: np.ndarray) -> np.ndarray:
                x = x - np.min(x)
                s = np.sum(x)
                if s <= 0:
                    return np.full_like(x, 1.0 / x.size)
                return x / s
            p_n = _norm(p_arr)
            q_n = _norm(q_arr)
            return float(np.sum(np.abs(p_n - q_n)))  # in [0,2]
        except Exception:
            return 0.0  # fail-open


class DROGate:
    """Dynamic Risk Optimization gate with probabilistic rejection.

    evaluate(...) returns a dict with allow flag & diagnostics.
    Gate can be disabled by config or activation criteria (min 72h acceptance).
    """

    def __init__(self, cfg: Dict[str, Any] | None, acceptance_metrics: Dict[str, Any] | None = None):
        cfg = cfg or {}
        self.enabled_cfg = bool(cfg.get('enabled', False))
        self.k = float(cfg.get('k', 6.0))
        self.mid = float(cfg.get('mid', 0.5))
        self.hazard_source = str(cfg.get('hazard_source', 'efe')).lower()
        self.blend = float(min(1.0, max(0.0, cfg.get('blend_sinkhorn', 0.5))))
        self.enable_min_72h = int(cfg.get('enable_min_72h', 0) or 0)
        self.random_seed_bias = int(cfg.get('seed_bias', 1337) or 1337)
        self.acceptance_metrics = acceptance_metrics or {}
        self.sinkhorn = OTSinkhornStub()
        self.active = self._activation_ok()

    # --- Internal helpers -------------------------------------------------
    def _activation_ok(self) -> bool:
        if not self.enabled_cfg:
            return False
        if self.enable_min_72h > 0:
            last72 = self.acceptance_metrics.get('last_72h')
            if last72 is None or last72 < self.enable_min_72h:
                return False
        return True

    @staticmethod
    def _norm_metric(x: float) -> float:
        try:
            if x is None or not math.isfinite(x):
                return 0.0
            return max(0.0, min(1.0, x / (x + 10.0)))
        except Exception:
            return 0.0

    def _base_metric(self, efe: float | None, empowerment: float | None) -> float:
        if self.hazard_source == 'empowerment':
            return self._norm_metric(empowerment or 0.0)
        if self.hazard_source == 'random':
            # Deterministic random based on seed_bias and coarse efe bucket
            bucket = int((efe or 0.0) * 1000) // 5
            rnd = random.Random(self.random_seed_bias + bucket)
            return rnd.random()
        # default: efe
        return self._norm_metric(efe or 0.0)

    # --- Public API -------------------------------------------------------
    def evaluate(self, *, efe: float | None, empowerment: float | None) -> Dict[str, Any]:
        if not self.active:
            return {
                'allow': True,
                'enabled': False,
                'reason': 'inactive',
                'hazard': 0.0,
                'rho': 0.0,
                'blocked_prob': 0.0,
                'u': 0.0,
            }
        try:
            base = self._base_metric(efe, empowerment)
            # Build simple paired vectors for sinkhorn from metrics
            p = [efe or 0.0, empowerment or 0.0]
            q = [empowerment or 0.0, efe or 0.0]
            cost = self.sinkhorn.distance(p, q)  # in [0,2]
            c_norm = cost / (cost + 1.0)  # (0,1)
            H = (1 - self.blend) * base + self.blend * c_norm
            # Logistic
            rho = 1.0 / (1.0 + math.exp(-self.k * (H - self.mid)))
            # Deterministic uniform sample (seed by rounded hazard & bias)
            seed = int(H * 10_000) + self.random_seed_bias
            rnd = random.Random(seed)
            u = rnd.random()
            allow = u >= rho  # block with probability rho(H)
            return {
                'allow': allow,
                'enabled': True,
                'reason': None if allow else 'dro_gate_block',
                'hazard': H,
                'base_metric': base,
                'sinkhorn_norm': c_norm,
                'rho': rho,
                'blocked_prob': rho,
                'u': u,
            }
        except Exception as e:  # fail-open
            return {
                'allow': True,
                'enabled': True,
                'reason': f'error:{e.__class__.__name__}',
                'hazard': 0.0,
                'rho': 0.0,
                'blocked_prob': 0.0,
                'u': 0.0,
            }


__all__ = [
    'DROGate',
    'OTSinkhornStub',
]
