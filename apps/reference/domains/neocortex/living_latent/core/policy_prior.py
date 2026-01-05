# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple
import json
import math


@dataclass
class LinearPrior:
    # Simple linear regressor: y = w^T x + b
    w: List[float]
    b: float

    def predict(self, x: Sequence[float]) -> float:
        return float(sum((self.w[i] if i < len(self.w) else 0.0) * float(xi) for i, xi in enumerate(x)) + self.b)

    def state_dict(self) -> dict:
        return {"w": list(self.w), "b": float(self.b)}

    @staticmethod
    def from_state_dict(d: dict) -> "LinearPrior":
        return LinearPrior(w=[float(v) for v in d.get("w", [])], b=float(d.get("b", 0.0)))


def fit_linear_prior(X: Sequence[Sequence[float]], y: Sequence[float]) -> LinearPrior:
    """Closed-form ridge=1e-6 linear regression with bias term.
    X: n x d, y: n
    """
    import numpy as np

    X = np.array(X, dtype=float)
    y = np.array(y, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    # add bias column
    ones = np.ones((X.shape[0], 1))
    Xb = np.concatenate([X, ones], axis=1)
    # ridge for stability
    lam = 1e-6
    A = Xb.T @ Xb + lam * np.eye(Xb.shape[1])
    w_full = np.linalg.pinv(A) @ (Xb.T @ y)
    w = w_full[:-1]
    b = w_full[-1]
    return LinearPrior(w=w.tolist(), b=float(b))
