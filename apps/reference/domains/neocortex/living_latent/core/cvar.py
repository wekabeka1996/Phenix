import numpy as np
from typing import Dict, Any, Optional


def cvar_tail(x: np.ndarray, alpha: float) -> float:
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return 0.0
    q = float(np.quantile(x, alpha))
    tail = x[x >= q]
    return float(tail.mean()) if tail.size else q


def guess_risk_scale(meta: Dict[str, Any]) -> float:
    for k in ("arma_sigma2", "sigma2", "energy", "efe"):
        v = meta.get(k)
        try:
            v = float(v)
            if v > 0:
                return max(v, 1e-8)
        except Exception:
            pass
    return 1.0


def draw_risk_samples(meta: Dict[str, Any], n: int, seed: Optional[int] = None) -> np.ndarray:
    rng = np.random.default_rng(seed)
    scale = float(np.sqrt(guess_risk_scale(meta)))
    # heavy-tailed samples via Student-t
    return np.abs(rng.standard_t(df=5, size=int(n))) * float(scale)
