from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.reference.config_models import AuroraConfig
from apps.reference.domains.strategies.runtimes.alpha_mr_s01.handler import AlphaMrS01Handler

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


@dataclass(frozen=True)
class AlphaMrS01Plugin:
    strategy_id: str = "alpha_mr_s01"

    def create_handler(self, *, fsm: "FSMCore", config: AuroraConfig) -> AlphaMrS01Handler:
        return AlphaMrS01Handler(fsm=fsm, config=config)
