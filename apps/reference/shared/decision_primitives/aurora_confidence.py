from __future__ import annotations

import math
from typing import Any


def _coerce_finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def compute_aurora_strategy_confidence(
    *,
    score: Any,
    threshold_factor: Any,
) -> float | None:
    score_value = _coerce_finite_float(score)
    if score_value is None:
        return None

    factor_value = _coerce_finite_float(threshold_factor)
    if factor_value is None or factor_value == 0.0:
        factor_value = 1.0

    if factor_value > 0.0:
        return min(1.0, abs(score_value) / factor_value)

    return 0.5
