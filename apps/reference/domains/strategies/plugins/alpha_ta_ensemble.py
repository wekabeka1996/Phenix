from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.reference.config_models import AuroraConfig
from apps.reference.domains.strategies.runtimes.alpha_ta_ensemble.handler import AlphaTaEnsembleHandler

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


@dataclass(frozen=True)
class AlphaTaEnsemblePlugin:
    strategy_id: str = "alpha_ta_ensemble"

    def create_handler(self, *, fsm: "FSMCore", config: AuroraConfig) -> AlphaTaEnsembleHandler:
        return AlphaTaEnsembleHandler(fsm=fsm, config=config)
