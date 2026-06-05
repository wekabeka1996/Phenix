from __future__ import annotations

from typing import Dict, Tuple

from ._common import require_param


def evaluate_execution(
    *,
    spread_bps: float,
    liquidity_state: float,
    projected_exposure_usd: float,
    max_exposure_usd: float,
    params: Dict[str, float],
) -> Tuple[float, Dict[str, float]]:
    if spread_bps < 0.0 or liquidity_state < 0.0 or projected_exposure_usd < 0.0:
        raise ValueError("execution inputs must be >= 0")
    if max_exposure_usd <= 0.0:
        raise ValueError("max_exposure_usd must be > 0")

    omega_liquidity = require_param(params, "omega_liquidity")
    phi_spread_drag = require_param(params, "phi_spread_drag")
    phi_notional_pressure = require_param(params, "phi_notional_pressure")

    liquidity_reward = liquidity_state * omega_liquidity
    spread_drag = -(spread_bps * phi_spread_drag)
    notional_pressure = projected_exposure_usd / max_exposure_usd
    notional_penalty = -(phi_notional_pressure * (notional_pressure / max(liquidity_state, 1e-6)))

    total = liquidity_reward + spread_drag + notional_penalty
    return total, {
        "liquidity_reward": liquidity_reward,
        "spread_drag": spread_drag,
        "notional_pressure": notional_pressure,
        "notional_penalty": notional_penalty,
    }
