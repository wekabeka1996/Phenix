from __future__ import annotations

from typing import Dict, Tuple

from ._common import require_param


def evaluate_risk(
    *,
    current_exposure_usd: float,
    projected_exposure_usd: float,
    max_exposure_usd: float,
    volatility_state: float,
    params: Dict[str, float],
) -> Tuple[float, Dict[str, float]]:
    if current_exposure_usd < 0.0 or projected_exposure_usd < 0.0:
        raise ValueError("exposure inputs must be >= 0")
    if max_exposure_usd <= 0.0:
        raise ValueError("max_exposure_usd must be > 0")
    if volatility_state < 0.0:
        raise ValueError("volatility_state must be >= 0")

    phi_inventory = require_param(params, "phi_inventory")
    phi_overflow = require_param(params, "phi_overflow")
    phi_volatility = require_param(params, "phi_volatility")

    current_util = current_exposure_usd / max_exposure_usd
    projected_util = projected_exposure_usd / max_exposure_usd
    headroom = max(0.0, 1.0 - current_util)
    overflow = max(0.0, projected_util - 1.0)

    inventory_penalty = -phi_inventory * (projected_util ** 2)
    overflow_penalty = -phi_overflow * (overflow ** 2 if overflow > 0.0 else 0.0)
    volatility_penalty = -(phi_volatility * volatility_state * max(0.0, projected_util))
    total = inventory_penalty + overflow_penalty + volatility_penalty
    return total, {
        "current_utilization": current_util,
        "projected_utilization": projected_util,
        "headroom_ratio": headroom,
        "inventory_penalty": inventory_penalty,
        "overflow_penalty": overflow_penalty,
        "volatility_penalty": volatility_penalty,
    }
