"""
Internal dataclass types for ExecPosRuntimeV2.

These structs are used inside the execution_position domain after boundary
payloads have been validated by Pydantic models in contracts.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Any, Dict


@dataclass
class RuntimeEntryIntent:
    """Canonical runtime intent for ENTRY_INTENT events."""

    symbol: str
    side: str
    quantity: Decimal
    price: Optional[Decimal]
    price_ref: Optional[Decimal]
    order_type: str
    time_in_force: Optional[str]

    rid: Optional[str] = None
    strategy_id: Optional[str] = None
    idempotent_key: Optional[str] = None
    client_order_id: Optional[str] = None
    why: Optional[str] = None


@dataclass
class ExecutionResult:
    """Standardized execution result for adapter operations."""

    success: bool
    error_kind: Optional[str] = None
    is_timeout: bool = False
    is_rate_limited: bool = False

    symbol: Optional[str] = None
    order_type: Optional[str] = None
    client_order_id: Optional[str] = None

    adapter_payload: Dict[str, Any] = field(default_factory=dict)
    why: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Utility for returning a dict view (for tests/legacy callers)."""
        return {
            "success": self.success,
            "error_kind": self.error_kind,
            "is_timeout": self.is_timeout,
            "is_rate_limited": self.is_rate_limited,
            "symbol": self.symbol,
            "order_type": self.order_type,
            "client_order_id": self.client_order_id,
            "adapter_payload": self.adapter_payload,
            "why": self.why,
        }
