from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

SimulationOutcome = Literal[
    "NOT_FILLED_TIMEOUT",
    "FILLED_TP",
    "FILLED_SL",
    "FILLED_TIMEOUT",
    "AMBIGUOUS_INTRABAR",
    "ERROR"
]

class ShadowSimulationResult(BaseModel):
    """Result of replaying one ShadowEntryPlan against historical data."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str
    cycle_key: str
    symbol: str
    ts_ms: int
    entry_side: str
    confidence_tier: str
    
    limit_price: float
    tp_price: float
    sl_price: float
    
    outcome: SimulationOutcome
    outcome_reason: Optional[str] = None
    
    fill_ts_ms: Optional[int] = None
    fill_price: Optional[float] = None
    fill_bar_idx: Optional[int] = None
    
    exit_ts_ms: Optional[int] = None
    exit_price: Optional[float] = None
    exit_bar_idx: Optional[int] = None
    
    duration_bars: Optional[int] = None
    
    gross_pnl_pct: float = 0.0
    net_pnl_pct: float = 0.0
    fees_paid_pct: float = 0.0
