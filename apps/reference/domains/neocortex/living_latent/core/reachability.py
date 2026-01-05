# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""R1-3 Reachability & Safety Gate

simulate_reachability(bridge) -> feasibility in [0,1].

Current heuristic proxy (R1-lite):
  - Start from 1.0
  - Subtract normalized energy_cost * w_energy
  - Subtract latency_risk * w_latency
  - Subtract penalty_acf * w_acf
  - Clamp to [0,1]

Bridge dict expected keys (optional, default 0): energy_cost, latency_risk, penalty_acf.
Weights chosen conservatively; will be replaced by model-based rollout in R2.
"""
from __future__ import annotations
from typing import Dict, Any

W_ENERGY = 0.35
W_LATENCY = 0.30
W_ACF = 0.25

def simulate_reachability(bridge: Dict[str, Any]) -> float:
    energy = float(bridge.get('energy_cost', 0.0))
    latency = float(bridge.get('latency_risk', 0.0))
    acf = float(bridge.get('penalty_acf', 0.0))
    feasibility = 1.0 - (energy * W_ENERGY + latency * W_LATENCY + acf * W_ACF)
    if feasibility < 0.0:
        feasibility = 0.0
    if feasibility > 1.0:
        feasibility = 1.0
    return feasibility

def is_reachable(bridge: Dict[str, Any], min_feasibility: float) -> bool:
    """Return True if simulated feasibility >= min_feasibility."""
    return simulate_reachability(bridge) >= float(min_feasibility)
