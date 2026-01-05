# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from typing import Dict, Tuple
import math
import random


_BOUNDS: Dict[str, Tuple[float, float]] = {
    "p": (0.0, 1.0),
    "q": (0.0, 1.0),
    "lam": (0.0, 2.0),
    "kappa": (0.0, 2.0),
    "rho": (0.0, 1.0),
    "ups": (0.0, 1.0),
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class Genome:
    p: float
    q: float
    lam: float
    kappa: float
    rho: float
    ups: float

    @staticmethod
    def bounds() -> Dict[str, Tuple[float, float]]:
        return dict(_BOUNDS)

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    # Human-friendly alias for policy/prior export
    def to_hparams(self) -> Dict[str, float]:
        return self.to_dict()

    @staticmethod
    def from_hparams(h: Dict[str, float]) -> "Genome":
        return Genome(**h)

    @staticmethod
    def sample(seed: int | None = None) -> "Genome":
        rnd = random.Random(seed)
        return Genome(
            p=rnd.random(),
            q=rnd.random(),
            lam=2.0 * rnd.random(),
            kappa=2.0 * rnd.random(),
            rho=rnd.random(),
            ups=rnd.random(),
        )

    def mutate(self, seed: int | None = None, scale: float = 0.1) -> "Genome":
        rnd = random.Random(seed)
        vals = asdict(self)
        out: Dict[str, float] = {}
        for k, v in vals.items():
            lo, hi = _BOUNDS[k]
            # Gaussian perturbation scaled by range
            rng = hi - lo
            nv = v + rnd.gauss(0.0, scale * rng)
            out[k] = _clamp(nv, lo, hi)
        return replace(self, **out)
