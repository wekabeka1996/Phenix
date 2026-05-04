"""
Normalized error codes for distributed idempotency layer.

All errors enforce WHY ≤ 80 characters.
"""

from typing import Optional


class IdempotencyError(Exception):
    """Base exception for idempotency layer errors."""

    code: str = "ERR.idemp.base"

    def __init__(self, why: str, details: Optional[str] = None) -> None:
        """
        Initialize idempotency error.

        Args:
            why: Human-readable explanation (≤80 chars)
            details: Optional extended information

        Raises:
            ValueError: If why > 80 characters
        """
        if len(why) > 80:
            raise ValueError(f"WHY must be ≤80 chars, got {len(why)}: {why[:80]}...")

        self.why = why
        self.details = details

        # Format message
        msg = f"{self.code}: {why}"
        if details:
            msg += f" | {details}"

        super().__init__(msg)


class ConflictError(IdempotencyError):
    """Idempotency conflict - different payload_digest for same key."""

    code: str = "ERR.idemp.conflict"

    def __init__(self, key: str, expected_digest: str, actual_digest: str) -> None:
        """
        Initialize conflict error.

        Args:
            key: Idempotent key
            expected_digest: Digest of current request
            actual_digest: Digest of existing record
        """
        why = f"idemp conflict: key={key[:20]}"
        details = f"expected={expected_digest[:16]}, got={actual_digest[:16]}"
        super().__init__(why=why, details=details)


class BusyError(IdempotencyError):
    """Idempotency key held by external owner."""

    code: str = "ERR.idemp.busy"

    def __init__(self, key: str, owner: str) -> None:
        """
        Initialize busy error.

        Args:
            key: Idempotent key
            owner: External owner holding the key
        """
        why = f"idemp busy: key={key[:20]}, owner={owner[:20]}"
        super().__init__(why=why)


class TimeoutError(IdempotencyError):
    """Idempotency store operation timed out."""

    code: str = "ERR.idemp.timeout"

    def __init__(self, operation: str, timeout_ms: int, elapsed_ms: int) -> None:
        """
        Initialize timeout error.

        Args:
            operation: Operation name (reserve/confirm/release)
            timeout_ms: Configured timeout
            elapsed_ms: Actual elapsed time
        """
        why = f"idemp timeout: {operation} {elapsed_ms}ms > {timeout_ms}ms"
        super().__init__(why=why)


class CBOpenError(IdempotencyError):
    """Circuit breaker open for idempotency store."""

    code: str = "ERR.idemp.cb_open"

    def __init__(self, operation: str) -> None:
        """
        Initialize CB open error.

        Args:
            operation: Operation name
        """
        why = f"cb open: idemp {operation}"
        super().__init__(why=why)


class MissingError(IdempotencyError):
    """Idempotency record not found."""

    code: str = "ERR.idemp.missing"

    def __init__(self, key: str, operation: str) -> None:
        """
        Initialize missing error.

        Args:
            key: Idempotent key
            operation: Operation attempted (confirm/release)
        """
        why = f"idemp missing: {operation} key={key[:30]}"
        super().__init__(why=why)


class StoreError(IdempotencyError):
    """Generic store backend error."""

    code: str = "ERR.idemp.store"

    def __init__(self, operation: str, backend_error: str) -> None:
        """
        Initialize store error.

        Args:
            operation: Operation name
            backend_error: Backend-specific error message
        """
        why = f"idemp store: {operation} failed"
        details = backend_error[:60] if backend_error else None
        super().__init__(why=why, details=details)
