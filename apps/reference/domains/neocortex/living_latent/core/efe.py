# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

# WRITE PRODUCTION-READY PYTHON 3.11.
# Follow this SPEC EXACTLY. type hints, pydantic for IO, no global state, dependency injection via constructors.
# Logging: structured JSON to logs/*.jsonl. Handle exceptions gracefully and continue.
# Every public function must have a docstring with Args/Returns/Raises.

# SPEC EFE:
# ExpectedFreeEnergy: compute(obs)->float; expose components (surprisal, disagreement).

import logging
from typing import Optional

from .config import EFEConfig
from .telemetry import Observation
from .world import WorldEnsemble

log = logging.getLogger(__name__)

class EMA:
    """Exponential Moving Average filter."""
    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self.value: Optional[float] = None

    def update(self, new_value: float) -> float:
        if self.value is None:
            self.value = new_value
        else:
            self.value = self.alpha * new_value + (1 - self.alpha) * self.value
        return self.value

class ExpectedFreeEnergy:
    """
    Computes the Expected Free Energy (EFE) as a weighted sum of surprisal (NLL)
    and disagreement (ensemble variance), representing the agent's uncertainty.
    """
    def __init__(self, config: EFEConfig, world_ensemble: WorldEnsemble):
        """
        Initializes the EFE calculator.

        Args:
            config: The EFE configuration object.
            world_ensemble: The trained world model ensemble.
        """
        self.config = config
        self.world = world_ensemble
        self._surprisal_ema = EMA(alpha=0.1)
        self._disagreement_ema = EMA(alpha=0.1)
        self.last_surprisal: float = 0.0
        self.last_disagreement: float = 0.0

    def compute(self, obs: Observation) -> float:
        """
        Computes the smoothed EFE for a given observation.

        Args:
            obs: The current telemetry observation.

        Returns:
            The calculated EFE value.
        """
        self.last_surprisal = self.world.nll(obs)
        self.last_disagreement = self.world.disagreement(obs)

        smoothed_surprisal = self._surprisal_ema.update(self.last_surprisal)
        smoothed_disagreement = self._disagreement_ema.update(self.last_disagreement)
        
        efe = (
            self.config.surprisal_weight * smoothed_surprisal +
            self.config.disagreement_weight * smoothed_disagreement
        )
        return efe

    @property
    def surprisal(self) -> float:
        """Returns the latest raw surprisal value."""
        return self.last_surprisal

    @property
    def disagreement(self) -> float:
        """Returns the latest raw disagreement value."""
        return self.last_disagreement

# Example Usage
if __name__ == '__main__':
    import time
    from pathlib import Path
    from .config import load_config
    from .telemetry import Telemetry

    print("--- Initializing EFE components ---")
    cfg = load_config(Path("cfg/master.yaml"))
    world = WorldEnsemble(cfg.efe)
    efe_calculator = ExpectedFreeEnergy(cfg.efe, world)
    telemetry = Telemetry(mock_mode=True)
    
    print("\n--- Computing EFE over 10 steps ---")
    for i in range(10):
        obs = telemetry.poll()
        # Update the world model to make it learn something
        world.update(obs)
        
        efe_value = efe_calculator.compute(obs)
        print(
            f"Step {i+1}: "
            f"Surprisal={efe_calculator.surprisal:.2f}, "
            f"Disagreement={efe_calculator.disagreement:.4f} -> "
            f"EFE={efe_value:.3f}"
        )
        time.sleep(0.2)
