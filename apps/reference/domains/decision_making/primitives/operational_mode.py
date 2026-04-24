"""Operational mode helpers for Aurora decision-making runtime.

The SSOT for allowed mode values lives in config_models. This module only
normalizes that validated input and applies the narrow runtime overrides that
are currently implemented.
"""

import logging
from typing import Any, Dict

from apps.reference.config_models import MemoryShieldConfig, OperationalMode


LOG = logging.getLogger(__name__)


class ModeManager:
    """
    Apply the limited runtime behavior toggles exposed by OperationalMode.

    Current live runtime usage is the memory-shield override path consumed from
    Aurora scoring. ``get_overrides()`` is retained for tests and tooling that
    still inspect the override map directly.
    """

    def __init__(self, mode: OperationalMode | str):
        # Normalize to the SSOT enum so unsupported raw strings fail closed
        # instead of silently degrading to a no-op override set.
        self.mode = OperationalMode(mode)
        LOG.info("ModeManager initialized in %s mode.", self.mode)

    def get_overrides(self) -> Dict[str, Any]:
        """
        Return a shallow override map for diagnostics, tests, and tools.

        The structure mirrors the relevant DecisionConfig branches where
        practical, but the runtime path should prefer typed helpers such as
        ``apply_memory_shield_overrides()``.
        """
        overrides = {}

        if self.mode == OperationalMode.CURIOUS:
            LOG.info("Applying CURIOUS mode overrides (relaxed memory shield).")
            overrides["memory_shield"] = {
                "unknown_multiplier": 1.0,
                "exploring_multiplier": 1.0,
                "known_multiplier": 1.0
            }

        return overrides

    def apply_memory_shield_overrides(self, config: MemoryShieldConfig) -> MemoryShieldConfig:
        """
        Return a typed MemoryShieldConfig with any active mode overrides applied.

        PARANOID mode preserves the validated config as-is. CURIOUS mode copies
        the model and lifts the familiarity multipliers to ``1.0`` so unknown or
        exploring states are no longer penalized by the memory shield.
        """
        if self.mode == OperationalMode.CURIOUS:
            new_config = config.model_copy(update={
                "unknown_multiplier": 1.0,
                "exploring_multiplier": 1.0,
                "known_multiplier": 1.0
            })
            return new_config

        return config
