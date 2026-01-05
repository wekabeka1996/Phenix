# SPDX-License-Identifier: MIT
import math, time
from typing import Optional, Dict, Any
import numpy as np

try:
    # опционально: забираем эвристику масштаба из cvar.py, если есть
    from .cvar import guess_risk_scale  # type: ignore
except Exception:  # fallback
    def guess_risk_scale(meta: Dict[str, Any]) -> float:
        for k in ("arma_sigma2", "sigma2", "energy", "efe", "ood"):
            try:
                v = float(meta.get(k, 0.0))
                if v > 0:
                    return max(v, 1e-8)
            except Exception:
                pass
        return 1.0

def _sf(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default

def _surrogate_base(meta: Dict[str, Any]) -> float:
    # позитивные «риск-индикаторы» как суррогат лосса
    energy = _sf(meta.get("energy"), 0.0)
    efe    = _sf(meta.get("efe"),    0.0)
    ood    = _sf(meta.get("ood"),    0.0)
    sigma2 = _sf(meta.get("arma_sigma2"), 0.0)  # диагностика временных рядов
    # валентность скорей «полезность», уменьшаем риск чуть-чуть
    val    = _sf(meta.get("valence"), 0.0)
    base = max(energy + efe + ood + sigma2 - 0.1*val, 0.0)
    return base

def draw_risk_samples(
    meta: Dict[str, Any],
    n: int,
    seed: Optional[int] = None,
    mode: str = "mc",
) -> np.ndarray:
    """
    Возвращает массив неотрицательных «risk/loss» сэмплов длины n.
    mode:
      - "mc": имитация MC-dropout/стох. инференса
      - "ensemble": имитация ансамбля (более широкие хвосты)
      - иное → heavy-tail fallback (t с df=5)
    """
    rng = np.random.default_rng(None if seed is None else int(seed))
    n = max(int(n), 1)
    scale = math.sqrt(max(_sf(guess_risk_scale(meta), 1.0), 1e-12))
    base  = _surrogate_base(meta)

    if mode == "mc":
        # шум ~N(0, scale); иногда хвосты t, чтобы поднять CVaR
        noise = rng.normal(0.0, scale, size=n)
        mask  = rng.random(n) < 0.1
        if mask.sum() > 0:
            noise[mask] += rng.standard_t(df=5, size=int(mask.sum())) * scale
        samples = np.abs(base + noise)

    elif mode == "ensemble":
        # смесь нормалей с слегка большей дисперсией
        noise = rng.normal(0.0, 1.5*scale, size=n)
        samples = np.abs(base + noise)

    else:
        samples = np.abs(rng.standard_t(df=5, size=n) * scale)

    # гарантия float64 и неотрицательности
    return samples.astype(np.float64, copy=False)
