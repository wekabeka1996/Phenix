from __future__ import annotations

import logging
from typing import Any

from apps.reference.config_models import MemoryShieldConfig, OperationalMode


logger = logging.getLogger(__name__)


class ModeManager:
    """Apply runtime config overrides for the selected operational mode."""

    def __init__(self, mode: OperationalMode | str):
        if isinstance(mode, OperationalMode):
            self.mode = mode
        else:
            try:
                self.mode = OperationalMode(str(mode))
            except ValueError as exc:
                raise ValueError(
                    f"Unsupported operational mode: {mode}") from exc
        logger.info("ModeManager initialized in %s mode.", self.mode)

    def get_overrides(self) -> dict[str, Any]:
        overrides: dict[str, Any] = {}

        if self.mode == OperationalMode.CURIOUS:
            logger.info("Applying CURIOUS mode overrides (relaxed shields).")
            overrides["memory_shield"] = {
                "unknown_multiplier": 1.0,
                "exploring_multiplier": 1.0,
                "known_multiplier": 1.0,
            }

        return overrides

    def apply_memory_shield_overrides(
        self, config: MemoryShieldConfig
    ) -> MemoryShieldConfig:
        if self.mode == OperationalMode.CURIOUS:
            return config.model_copy(
                update={
                    "unknown_multiplier": 1.0,
                    "exploring_multiplier": 1.0,
                    "known_multiplier": 1.0,
                }
            )

        return config
