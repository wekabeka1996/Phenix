"""
Execution Adapter Exceptions (FSMP-P2-T01)

Normalized error classes for SDK → ERR code mapping.
All exceptions include ERR.code + WHY (≤80 chars).
"""
from __future__ import annotations

from typing import Optional


class AdapterError(Exception):
    """Base class for all adapter errors."""
    
    code: str = "ERR.adapter.unknown"
    
    def __init__(self, why: str, code: Optional[str] = None, details: Optional[str] = None) -> None:
        """
        Initialize adapter error.
        
        Args:
            why: Short explanation (≤80 chars)
            code: Optional override for ERR code
            details: Optional detailed message
        """
        self.why = why[:80]  # Enforce ≤80 chars
        if code:
            self.code = code
        self.details = details
        
        msg = f"{self.code}: {self.why}"
        if details:
            msg += f" | {details}"
        super().__init__(msg)


class AdapterTimeoutError(AdapterError):
    """SDK operation exceeded timeout threshold."""
    
    code: str = "ERR.adapter.timeout"
    
    def __init__(
        self,
        operation: str,
        timeout_ms: int,
        actual_ms: Optional[int] = None
    ) -> None:
        """
        Initialize timeout error.
        
        Args:
            operation: Operation name (submit|cancel|stream)
            timeout_ms: Configured timeout limit
            actual_ms: Actual elapsed time (if known)
        """
        if actual_ms:
            why = f"Timeout {operation} {actual_ms}ms > {timeout_ms}ms limit"
        else:
            why = f"Timeout {operation} exceeded {timeout_ms}ms limit"
        
        super().__init__(why=why)


class CBOpenError(AdapterError):
    """Circuit breaker is open - operation suppressed."""
    
    code: str = "ERR.adapter.cb_open"
    
    def __init__(self, operation: str) -> None:
        """
        Initialize CB open error.
        
        Args:
            operation: Operation name (submit|cancel)
        """
        why = f"CB open: {operation} suppressed"
        super().__init__(why=why)


class IdempotentDuplicateError(AdapterError):
    """Duplicate idempotent operation - no-op."""
    
    code: str = "ERR.adapter.idempotent_duplicate"
    
    def __init__(self, key: str) -> None:
        """
        Initialize idempotent duplicate error.
        
        Args:
            key: Idempotency key
        """
        # Truncate key if too long
        key_short = key[:40] + "..." if len(key) > 40 else key
        why = f"Idempotent duplicate: no-op (key={key_short})"
        super().__init__(why=why)


class SDKError(AdapterError):
    """SDK returned an error response."""
    
    code: str = "ERR.adapter.sdk_error"
    
    def __init__(
        self,
        operation: str,
        sdk_code: Optional[str] = None,
        sdk_message: Optional[str] = None
    ) -> None:
        """
        Initialize SDK error.
        
        Args:
            operation: Operation name (submit|cancel|stream)
            sdk_code: SDK-specific error code
            sdk_message: SDK error message
        """
        if sdk_code:
            why = f"SDK error {operation}: {sdk_code}"
        else:
            why = f"SDK error {operation}"
        
        # Add SDK message as details if provided
        details = sdk_message if sdk_message else None
        
        super().__init__(why=why, details=details)


class RateLimitError(AdapterError):
    """Rate limit exceeded - too many requests."""
    
    code: str = "ERR.adapter.rate_limit"
    
    def __init__(self, retry_after_ms: Optional[int] = None) -> None:
        """
        Initialize rate limit error.
        
        Args:
            retry_after_ms: Suggested retry delay
        """
        if retry_after_ms:
            why = f"Rate limit exceeded, retry after {retry_after_ms}ms"
        else:
            why = "Rate limit exceeded"
        
        super().__init__(why=why)


class InvalidModeError(AdapterError):
    """Operation not allowed in current execution mode."""
    
    code: str = "ERR.adapter.invalid_mode"
    
    def __init__(self, operation: str, mode: str, required_mode: str) -> None:
        """
        Initialize invalid mode error.
        
        Args:
            operation: Operation name
            mode: Current execution mode
            required_mode: Required mode for operation
        """
        why = f"{operation} not allowed in mode={mode}, need {required_mode}"
        super().__init__(why=why)


class ConfigurationError(AdapterError):
    """Adapter configuration is invalid or missing."""
    
    code: str = "ERR.adapter.config"
    
    def __init__(self, missing_keys: list[str]) -> None:
        """
        Initialize configuration error.
        
        Args:
            missing_keys: List of missing ENV variables
        """
        keys_str = ", ".join(missing_keys[:3])  # Limit to first 3
        if len(missing_keys) > 3:
            keys_str += f" +{len(missing_keys) - 3} more"
        
        why = f"Missing ENV: {keys_str}"
        super().__init__(why=why)
