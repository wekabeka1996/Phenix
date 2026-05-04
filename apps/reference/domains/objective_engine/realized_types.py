from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.domains.objective_engine.types import ObjectiveTrace


@dataclass(frozen=True)
class ObjectiveSnapshot:
    strategy_id: str
    symbol: str
    entry_rid: str
    entry_side: str
    intent_ts_ms: int
    entry_price: Decimal
    stop_price: Optional[Decimal]
    target_price: Optional[Decimal]
    tf_sec: Optional[int]
    regime_entry: str
    pretrade_objective_trace: ObjectiveTrace
    signal_id: Optional[str] = None


@dataclass
class ActiveObjectivePosition:
    snapshot: ObjectiveSnapshot
    signed_qty: Decimal
    avg_entry_price: Decimal
    open_ts_ms: int
    last_fill_ts_ms: int
    highest_price: Decimal
    lowest_price: Decimal
    accrued_fees: Decimal = Decimal("0")
    regime_exit: Optional[str] = None
    regime_path_changes: int = 0
    last_regime: Optional[str] = None
    close_reason: Optional[str] = None
    raw_context: Dict[str, Any] = field(default_factory=dict)


class ObjectiveRealizedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    symbol: str
    entry_rid: str
    close_rid: str
    regime_entry: str
    regime_exit: str
    pretrade_objective_trace: Dict[str, Any]
    realized_components: Dict[str, float] = Field(default_factory=dict)
    realized_quality_score: float
    realized_pnl: float
    fees: float
    duration_sec: float
    mae: float
    mfe: float
    close_reason: str
    signal_id: Optional[str] = None
