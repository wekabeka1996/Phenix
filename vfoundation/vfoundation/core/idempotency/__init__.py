"""
Distributed idempotency layer for exactly-once semantics across multiple workers.

Source of truth: distributed store (Redis). No business logic.
"""
from .errors import (
    IdempotencyError,
    ConflictError,
    BusyError,
    TimeoutError as IdempotencyTimeoutError,
    CBOpenError,
    MissingError,
    StoreError,
)
from .store import (
    DistributedIdempotencyStore,
    ReserveResult,
    ConfirmResult,
    StatusResult,
    ReleaseResult,
    ReserveStatus,
    ConfirmStatus,
    GetStatus,
    ReleaseStatus,
)
from .idempotency import InflightState, IdempotencyStore

__all__ = [
    "IdempotencyError",
    "ConflictError",
    "BusyError",
    "IdempotencyTimeoutError",
    "CBOpenError",
    "MissingError",
    "StoreError",
    "DistributedIdempotencyStore",
    "ReserveResult",
    "ConfirmResult",
    "StatusResult",
    "ReleaseResult",
    "ReserveStatus",
    "ConfirmStatus",
    "GetStatus",
    "ReleaseStatus",
    "InflightState",
    "IdempotencyStore",
]
