from __future__ import annotations

from enum import Enum


class OperationalMode(str, Enum):
    PARANOID = "paranoid"
    CURIOUS = "curious"


class ExecutionGateName(str, Enum):
    HARD_VETO = "HARD_VETO"
    DIRECTION = "DIRECTION"
    THRESHOLD = "THRESHOLD"
    SHIELD = "SHIELD"
    STRUCTURAL = "STRUCTURAL"
    LIQUIDITY = "LIQUIDITY"


class DangerZoneExitType(str, Enum):
    TIGHTEN_STOPS = "TIGHTEN_STOPS"
    CLOSE_POSITION = "CLOSE_POSITION"


__all__ = [
    "DangerZoneExitType",
    "ExecutionGateName",
    "OperationalMode",
]
