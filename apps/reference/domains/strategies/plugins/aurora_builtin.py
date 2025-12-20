from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.reference.config_models import AuroraConfig

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


@dataclass(frozen=True)
class _NoopHandler:
    def register(self) -> None:
        return


@dataclass(frozen=True)
class AuroraBuiltinPlugin:
    """Placeholder plugin for the built-in Aurora (DM-driven) strategy."""

    strategy_id: str = "aurora"

    def create_handler(self, *, fsm: "FSMCore", config: AuroraConfig) -> _NoopHandler:
        return _NoopHandler()
