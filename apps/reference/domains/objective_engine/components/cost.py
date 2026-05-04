from __future__ import annotations

import math
from typing import Dict, Tuple

from ._common import require_param


def evaluate_cost(
    *,
    expected_fee_bps: float,
    expected_slippage_bps: float,
    spread_bps: float,
    params: Dict[str, float],
) -> Tuple[float, Dict[str, float]]:
    if expected_fee_bps < 0.0 or expected_slippage_bps < 0.0 or spread_bps < 0.0:
        raise ValueError("cost inputs must be >= 0")

    alpha_fee = require_param(params, "alpha_fee")
    alpha_slippage = require_param(params, "alpha_slippage")
    alpha_spread = require_param(params, "alpha_spread")

    fee_drag = -(expected_fee_bps * alpha_fee)
    slippage_drag = -(expected_slippage_bps * alpha_slippage)
    spread_drag = -(spread_bps * alpha_spread) * (1.0 + math.log1p(spread_bps / 10.0))
    total = fee_drag + slippage_drag + spread_drag
    return total, {
        "fee_drag": fee_drag,
        "slippage_drag": slippage_drag,
        "spread_drag": spread_drag,
    }
