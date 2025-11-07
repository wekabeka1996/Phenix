# apps/reference/orchestrator/types.py
"""
Type definitions for OrchestratorFSM.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime


class RIDLifecycle(Enum):
    """RID lifecycle states."""
    EVAL = "EVAL"        # Evaluating trade intent
    OPEN = "OPEN"        # Order opened
    MONITOR = "MONITOR"  # Monitoring position
    CLOSED = "CLOSED"    # Position closed


class OrchestratorEvent(Enum):
    """Events handled by OrchestratorFSM."""
    TRADE_INTENT_PROPOSED = "TRADE_INTENT_PROPOSED"
    ORDER_EXECUTED = "ORDER_EXECUTED"
    POSITION_CLOSED = "POSITION_CLOSED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class OrchestratorState(BaseModel):
    """State managed by OrchestratorFSM for each RID."""
    rid: str
    lifecycle: RIDLifecycle
    why_chain: List[str] = []
    created_at: datetime
    updated_at: datetime
    ttl_seconds: int = 3600  # 1 hour default
    idempotency_key: Optional[str] = None
    signed_cmd: Optional[Dict[str, Any]] = None
    circuit_breaker_active: bool = False
    error_count: int = 0

    class Config:
        arbitrary_types_allowed = True


class OrchestratorConfig(BaseModel):
    """Configuration for OrchestratorFSM."""
    max_rid_ttl_seconds: int = 86400  # 24 hours
    circuit_breaker_threshold: int = 5  # errors per hour
    enable_signing: bool = True
    signing_key_path: Optional[str] = None
