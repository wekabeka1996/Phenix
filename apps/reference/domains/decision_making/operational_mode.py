from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

from apps.reference.config_models import OperationalMode, ExecutionGateConfig, MemoryShieldConfig

logger = logging.getLogger(__name__)


class ModeManager:
    """
    Manages operational mode switching (PARANOID vs CURIOUS).
    Provides configuration overrides based on the active mode.
    """
    def __init__(self, mode: OperationalMode):
        self.mode = mode
        logger.info(f"ModeManager initialized in {self.mode} mode.")

    def get_overrides(self) -> Dict[str, Any]:
        """
        Return configuration overrides for the current mode.
        Structure matches the DecisionConfig hierarchy where possible,
        but primarily consumed by AuroraHandler to patch runtime components.
        """
        overrides = {}
        
        if self.mode == OperationalMode.CURIOUS:
            # CURIOUS Mode:
            # 1. Memory Shield: Relaxed (no penalty for unknown states)
            # 2. Threshold Gate: Lowered (explore weaker signals) - Optional/TODO
            
            logger.info("Applying CURIOUS mode overrides (Relaxed Shields).")
            
            # Override Memory Shield to effectively disable penalties (multiplier 1.0)
            # We don't change the config object directly, but provide values 
            # that can be used to patch/update the component.
            overrides["memory_shield"] = {
                "unknown_multiplier": 1.0,
                "exploring_multiplier": 1.0, 
                "known_multiplier": 1.0
            }
            
            # Potential Future Overrides:
            # overrides["execution_gate"] = {"soft_threshold": 0.15}
            
        elif self.mode == OperationalMode.PARANOID:
            # PARANOID Mode:
            # Strict adherence to config. No relaxations.
            pass
            
        return overrides

    def apply_memory_shield_overrides(self, config: MemoryShieldConfig) -> MemoryShieldConfig:
        """
        Apply mode-specific overrides to a MemoryShieldConfig copy.
        Returns a new (or modified) config object.
        """
        if self.mode == OperationalMode.CURIOUS:
            # Force multipliers to 1.0
            # We use model_copy(update=...) if pydantic v2
            # Or manually set since we might be updating a runtime instance
            
            # Create a copy to avoid mutating global config if shared (though usually passed by value/init)
            new_config = config.model_copy(update={
                "unknown_multiplier": 1.0,
                "exploring_multiplier": 1.0,
                "known_multiplier": 1.0
            })
            return new_config
            
        return config
