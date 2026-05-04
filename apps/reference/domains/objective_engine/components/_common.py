from __future__ import annotations

import math
from typing import Dict


def require_param(params: Dict[str, float], key: str) -> float:
    if key not in params:
        raise ValueError(f"objective component parameter missing: {key}")
    value = float(params[key])
    if not math.isfinite(value):
        raise ValueError(f"objective component parameter must be finite: {key}")
    return value

