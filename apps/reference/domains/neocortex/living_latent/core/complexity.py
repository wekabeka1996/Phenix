# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""Bridge Complexity Metrics (R0-Lite)

SPEC fragment (Road_map R0-07 / future R1 planning):
 - Provide a pluggable evaluator that computes a scalar complexity_score used for
   selecting among candidate bridges (default: mean step delta norm).
 - Expose additional diagnostic metrics (max_delta, curvature_proxy) for later
   analysis / potential multi-objective ranking.
 - Stateless, pure functions; deterministic given path.

The current implementation purposefully keeps the API minimal so that
`GuidedSlerpPlanner` can accept an optional evaluator without breaking older
code paths (fallback inline calculation when evaluator is None).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import numpy as np

@dataclass
class ComplexityResult:
    score: float
    metrics: Dict[str, float]

class ComplexityEvaluator:
    """Computes complexity related metrics for a bridge path.

    Contract:
      Input: path ndarray shape (T, D)
      Output: ComplexityResult with:
        - score: primary scalar (mean step delta norm)
        - metrics: auxiliary diagnostics (mean_delta, max_delta, std_delta, curvature_proxy)

    Error modes:
      * Empty or degenerate path (<2 points) => score 0.0, metrics zeros.
    """

    def compute(self, path: np.ndarray) -> ComplexityResult:  # pragma: no cover - trivial
        if not isinstance(path, np.ndarray) or path.ndim != 2 or path.shape[0] < 2:
            return ComplexityResult(0.0, {"mean_delta": 0.0, "max_delta": 0.0, "std_delta": 0.0, "curvature_proxy": 0.0})

        deltas = np.diff(path, axis=0)
        delta_norms = np.linalg.norm(deltas, axis=1)
        mean_delta = float(np.mean(delta_norms))
        max_delta = float(np.max(delta_norms))
        std_delta = float(np.std(delta_norms))
        # Curvature proxy: mean norm of second differences (discrete acceleration)
        if path.shape[0] > 2:
            second = np.diff(deltas, axis=0)
            curvature_proxy = float(np.mean(np.linalg.norm(second, axis=1)))
        else:
            curvature_proxy = 0.0
        score = mean_delta  # primary signal
        return ComplexityResult(score, {
            "mean_delta": mean_delta,
            "max_delta": max_delta,
            "std_delta": std_delta,
            "curvature_proxy": curvature_proxy,
        })

__all__ = ["ComplexityEvaluator", "ComplexityResult"]
