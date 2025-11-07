# apps/reference/orchestrator/__init__.py
"""
Orchestrator module for Phenix v1.

Provides centralized coordination for RID lifecycle, WHY chain aggregation,
TTL/GC management, circuit breaker, idempotency, and Ed25519 signing.
"""

from .orchestrator_fsm import OrchestratorFSM
from .types import OrchestratorState, OrchestratorEvent

__all__ = [
    "OrchestratorFSM",
    "OrchestratorState",
    "OrchestratorEvent",
]
