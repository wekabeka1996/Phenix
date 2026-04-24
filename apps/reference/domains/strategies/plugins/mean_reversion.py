from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.reference.config_models import AuroraConfig
from apps.reference.domains.strategies.runtimes.mean_reversion.handler import MeanReversionHandler

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


@dataclass(frozen=True)
class MeanReversionPlugin:
    strategy_id: str = "mean_reversion"

    def create_handler(self, *, fsm: "FSMCore", config: AuroraConfig) -> MeanReversionHandler:
        return MeanReversionHandler(fsm=fsm, config=config)
