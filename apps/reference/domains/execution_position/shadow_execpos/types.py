"""
Type definitions for the Shadow ExecPos architecture.
"""
from typing import Any, Dict, Optional, TypedDict, Union, List, Sequence
from enum import Enum
from dataclasses import dataclass, field

class ExecutionStatus(Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS" # Generic success for non-order ops

class ExecutionResult(TypedDict):
    """Result of an execution request."""
    status: ExecutionStatus
    success: bool
    order_id: Optional[str]
    client_order_id: Optional[str]
    error: Optional[str]
    metadata: Dict[str, Any]

class ExecutionCommand(TypedDict):
    """Normalized execution command."""
    verb: str  # PLACE, CANCEL, CLOSE
    symbol: str
    side: Optional[str]
    quantity: Optional[Union[str, float, int]]
    price: Optional[Union[str, float, int]]
    order_type: Optional[str] # LIMIT, MARKET, STOP_MARKET, etc.
    client_order_id: Optional[str]
    reduce_only: bool
    extra_params: Dict[str, Any]

class GateDecision(TypedDict):
    """Decision from the Gatekeeper."""
    allowed: bool
    reason: str
    modified_params: Dict[str, Any] # e.g. adjusted qty/price
    metadata: Dict[str, Any]

class WatchdogAction(Enum):
    NONE = "NONE"
    CANCEL_ORDER = "CANCEL_ORDER"
    PLACE_BRACKET = "PLACE_BRACKET"
    ALERT = "ALERT"
    SUPPRESS_BRACKETS = "SUPPRESS_BRACKETS"
    FORCE_SNAPSHOT = "FORCE_SNAPSHOT"

@dataclass
class WatchdogRecommendation:
    """Recommendation from the Watchdog with detailed violation information."""
    symbol: str
    side: str
    kind: str  # Violation kind: NO_SL, ORPHAN_SL, TOO_MANY_SL, MULTIPLE_META
    action: WatchdogAction
    target_id: Optional[str]  # Primary order ID
    reason: str
    orders_to_cancel: List[str]  # Order IDs to cancel
    details: Dict[str, Any]

class EnrichedTrade(TypedDict):
    """Trade payload enriched with price data."""
    original_payload: Dict[str, Any]
    price: str
    price_source: str # 'payload', 'position', 'quote'
    enriched: bool

@dataclass
class RuntimeEvent:
    """Event for ExecPosRuntimeV2 orchestration."""
    kind: str  # ENTRY_INTENT, CANCEL_INTENT, CLOSE_INTENT, TRADE_EXECUTED, POSITION_SNAPSHOT, ORDERS_SNAPSHOT
    symbol: str
    timestamp: float
    payload: Dict[str, Any] = field(default_factory=dict)
