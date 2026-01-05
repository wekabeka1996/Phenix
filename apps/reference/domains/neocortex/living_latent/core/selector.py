# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""R2 Attractor-aware bridge selector utilities.

Score formula: score = J - mu * dist2
Where:
  J      : expected improvement (plan.metadata['improvement'] or dJ)
  dist2  : squared Euclidean distance between candidate feature vector and current attractor center
  mu     : distance penalty multiplier (>=0)

Returns (score, accept, dist2)
"""
from __future__ import annotations
from typing import Sequence, Tuple, Optional, Any, Dict
import warnings
import json
from pathlib import Path

try:
    # Local import; optional to avoid hard dependency if module missing in older runs
    from .cvar_policy import cvar_gate
except Exception:  # pragma: no cover - safe fallback
    def cvar_gate(candidate: Any, baseline: Any, tau: float = 0.05, min_threshold: float = -0.10, enabled: bool = True):
        return True, {"enabled": False, "reason": "cvar_module_missing"}

def _get_cfg_cvar(cfg: Optional[Dict[str, Any]]) -> Tuple[bool, float, float, float, float]:
    """Extract CVaR settings from config dict with safe defaults.

    Returns: (enabled, tau, min_threshold, exp_weight, winsor_p)
    """
    if not cfg:
        return True, 0.05, -0.10, 0.0, 0.005
    r2 = cfg.get("r2", {})
    c = r2.get("cvar", {})
    enabled = bool(c.get("enabled", True))
    tau = float(c.get("tau", 0.05))
    min_threshold = float(c.get("min_threshold", -0.10))
    exp_weight = float(c.get("exp_weight", 0.0))
    winsor_p = float(c.get("winsor_p", 0.005))
    # Clamp with WARNs if out of range
    if exp_weight < 0.0 or exp_weight > 0.3:
        warnings.warn(
            f"r2.cvar.exp_weight={exp_weight} out of range [0,0.3]; clamping",
            RuntimeWarning,
            stacklevel=2,
        )
        exp_weight = max(0.0, min(0.3, exp_weight))
    if winsor_p < 0.0 or winsor_p > 0.5:
        warnings.warn(
            f"r2.cvar.winsor_p={winsor_p} out of range [0,0.5]; clamping",
            RuntimeWarning,
            stacklevel=2,
        )
        winsor_p = max(0.0, min(0.5, winsor_p))
    return enabled, tau, min_threshold, exp_weight, winsor_p

def evaluate_candidate(center: Sequence[float], features: Sequence[float], J: float, mu: float, min_score: float,
                       *, cfg: Optional[Dict[str, Any]] = None,
                       candidate_plan: Optional[Any] = None,
                       baseline_plan: Optional[Any] = None) -> Tuple[float,bool,float]:
    # Optional prior boost from distilled policy prior
    prior_boost = 0.0
    if cfg:
        prior_boost = float(cfg.get('r2', {}).get('router', {}).get('prior_boost', 0.0))
        # Clamp small sane range
        if prior_boost < 0.0 or prior_boost > 2.0:
            warnings.warn(f"r2.router.prior_boost={prior_boost} out of range [0,2]; clamping", RuntimeWarning, stacklevel=2)
            prior_boost = max(0.0, min(2.0, prior_boost))

    if not center:
        # Apply prior multiplier if present (no features distance)
        score = J * (1.0 + prior_boost)
        accept = score >= min_score
        # Optional CVaR gate
        enabled, tau, min_threshold, exp_weight, winsor_p = _get_cfg_cvar(cfg)
        if accept and candidate_plan is not None and baseline_plan is not None:
            ok, _ = cvar_gate(
                candidate_plan,
                baseline_plan,
                tau=tau,
                min_threshold=min_threshold,
                enabled=enabled,
                exp_weight=exp_weight,
                winsor_p=winsor_p,
            )
            accept = accept and ok
        return score, accept, 0.0
    vec = list(features)[:len(center)]
    if len(vec) < len(center):
        vec.extend([0.0]*(len(center)-len(vec)))
    dist2 = 0.0
    for c, v in zip(center, vec):
        d = (v - c)
        dist2 += d*d
    score = (J - mu * dist2) * (1.0 + prior_boost)
    accept = score >= min_score
    enabled, tau, min_threshold, exp_weight, winsor_p = _get_cfg_cvar(cfg)
    if accept and candidate_plan is not None and baseline_plan is not None:
        ok, _ = cvar_gate(
            candidate_plan,
            baseline_plan,
            tau=tau,
            min_threshold=min_threshold,
            enabled=enabled,
            exp_weight=exp_weight,
            winsor_p=winsor_p,
        )
        accept = accept and ok
    return score, accept, dist2

__all__ = ["evaluate_candidate"]
