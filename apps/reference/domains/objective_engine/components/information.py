from __future__ import annotations

from typing import Dict, Tuple

from ._common import require_param


def evaluate_information(
    *,
    regime_age_sec: float,
    regime_confidence: float,
    readiness_completeness: float,
    params: Dict[str, float],
) -> Tuple[float, Dict[str, float]]:
    if regime_age_sec < 0.0:
        raise ValueError("regime_age_sec must be >= 0")
    if not (0.0 <= regime_confidence <= 1.0):
        raise ValueError("regime_confidence must be in [0, 1]")
    if not (0.0 <= readiness_completeness <= 1.0):
        raise ValueError("readiness_completeness must be in [0, 1]")

    phi_staleness = require_param(params, "phi_staleness")
    omega_regime_confidence = require_param(params, "omega_regime_confidence")
    omega_readiness = require_param(params, "omega_readiness")

    staleness_penalty = -((regime_age_sec / 3600.0) * phi_staleness)
    confidence_reward = regime_confidence * omega_regime_confidence
    readiness_reward = readiness_completeness * omega_readiness
    total = staleness_penalty + confidence_reward + readiness_reward
    return total, {
        "staleness_penalty": staleness_penalty,
        "confidence_reward": confidence_reward,
        "readiness_reward": readiness_reward,
    }
