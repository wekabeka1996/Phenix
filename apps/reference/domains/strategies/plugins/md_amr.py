from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.reference.config_models import AuroraConfig
from apps.reference.domains.decision_making.md_amr_handler import MDAMRHandler

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


@dataclass(frozen=True)
class MDAMRPlugin:
    strategy_id: str = "md_amr"

    def create_handler(self, *, fsm: "FSMCore", config: AuroraConfig) -> MDAMRHandler:
        return MDAMRHandler(fsm=fsm, config=config)
