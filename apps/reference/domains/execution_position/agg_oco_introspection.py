"""Utilities for Aggregated OCO observability/introspection."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class AggOcoStateRow:
    """Normalized snapshot of aggregated OCO runtime state for (symbol, side)."""

    symbol: str
    side: str
    position_qty: Optional[str] = None
    position_source: Optional[str] = None
    position_updated_ts: Optional[float] = None
    avg_entry_price: Optional[str] = None
    sl_price: Optional[str] = None
    tp_price: Optional[str] = None
    bracket_set_id: Optional[str] = None
    bracket_version: Optional[int] = None
    bracket_created_ts: Optional[float] = None
    bracket_sl_order_id: Optional[str] = None
    bracket_tp_order_id: Optional[str] = None
    watchdog_status: str = "UNKNOWN"
    watchdog_updated_ts: Optional[float] = None
    watchdog_details: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe dictionary representation."""

        payload = asdict(self)
        # Drop None values for brevity
        return {key: value for key, value in payload.items() if value is not None}
