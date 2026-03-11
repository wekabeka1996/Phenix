from __future__ import annotations

from typing import Dict, Tuple

from ._common import require_param


def evaluate_edge(
    *,
    signal_score: float,
    threshold_margin: float,
    rr_expected: float,
    tp_dist_atr: float,
    stop_dist_atr: float,
    params: Dict[str, float],
) -> Tuple[float, Dict[str, float]]:
    if threshold_margin < 0.0 or rr_expected < 0.0 or tp_dist_atr < 0.0 or stop_dist_atr < 0.0:
        raise ValueError("edge inputs must be >= 0")

    omega_rr = require_param(params, "omega_rr")
    omega_threshold_margin = require_param(params, "omega_threshold_margin")
    phi_stop_distance = require_param(params, "phi_stop_distance")
    phi_rr_consistency = require_param(params, "phi_rr_consistency")

    rr_reward = rr_expected * omega_rr
    threshold_reward = threshold_margin * omega_threshold_margin
    stop_penalty = -(phi_stop_distance / max(stop_dist_atr, 1e-6))
    rr_geometry_penalty = -phi_rr_consistency * abs(tp_dist_atr - (rr_expected * stop_dist_atr))

    total = (abs(signal_score) * 0.25) + rr_reward + threshold_reward + stop_penalty + rr_geometry_penalty
    return total, {
        "rr_reward": rr_reward,
        "threshold_reward": threshold_reward,
        "stop_penalty": stop_penalty,
        "rr_geometry_penalty": rr_geometry_penalty,
    }
