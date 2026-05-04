"""
Error Taxonomy — Phase 17.1.

Structured error classification per Constitution audit findings.
Provides ErrorCategory enum, ErrorCode dataclass, and ErrorRegistry
for consistent error handling across vFoundation.

Additive-only: Does NOT modify existing IdempotencyError/AdapterError.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, List, Optional


class ErrorCategory(IntEnum):
    """Broad error categories with reserved numeric ranges."""

    VALIDATION = 1000
    TIMEOUT = 2000
    CIRCUIT_BREAKER = 3000
    IDEMPOTENCY = 4000
    SECURITY = 5000
    DR = 6000
    PROTOCOL = 7000
    INTERNAL = 9000


@dataclass(frozen=True)
class ErrorCode:
    """Immutable error code combining category + sub-code."""

    category: ErrorCategory
    sub_code: int
    label: str
    description: str = ""

    @property
    def code(self) -> int:
        """Unique numeric code = category + sub_code."""
        return int(self.category) + self.sub_code

    @property
    def full_label(self) -> str:
        """Human-readable label: ERR.<category_name>.<label>."""
        return f"ERR.{self.category.name}.{self.label}"


class ErrorRegistry:
    """Registry of known error codes with lookup by code or label."""

    def __init__(self) -> None:
        self._by_code: Dict[int, ErrorCode] = {}
        self._by_label: Dict[str, ErrorCode] = {}

    def register(self, ec: ErrorCode) -> None:
        """Register an error code. Raises ValueError on duplicate code."""
        if ec.code in self._by_code:
            raise ValueError(f"Error code {ec.code} already registered")
        self._by_code[ec.code] = ec
        self._by_label[ec.full_label] = ec

    def get(self, code: int) -> Optional[ErrorCode]:
        """Retrieve error code by numeric code."""
        return self._by_code.get(code)

    def get_by_label(self, label: str) -> Optional[ErrorCode]:
        """Retrieve error code by full label (ERR.CATEGORY.label)."""
        return self._by_label.get(label)

    def all_codes(self) -> List[ErrorCode]:
        """Return all registered error codes."""
        return list(self._by_code.values())

    def codes_in_category(self, category: ErrorCategory) -> List[ErrorCode]:
        """Return all error codes in a given category."""
        return [ec for ec in self._by_code.values() if ec.category == category]


def _build_standard_errors() -> ErrorRegistry:
    """Build pre-populated registry with standard error codes."""
    reg = ErrorRegistry()
    _standard = [
        ErrorCode(ErrorCategory.VALIDATION, 1, "INVALID_PAYLOAD", "Message payload failed schema validation"),
        ErrorCode(ErrorCategory.VALIDATION, 2, "MISSING_FIELD", "Required field is missing"),
        ErrorCode(ErrorCategory.TIMEOUT, 1, "ORDER_ACK_TIMEOUT", "Order acknowledgement timed out"),
        ErrorCode(ErrorCategory.TIMEOUT, 2, "ORDER_FILL_TIMEOUT", "Order fill timed out"),
        ErrorCode(ErrorCategory.CIRCUIT_BREAKER, 1, "CB_OPEN", "Circuit breaker is open"),
        ErrorCode(ErrorCategory.IDEMPOTENCY, 1, "DUPLICATE_REQUEST", "Duplicate request detected"),
        ErrorCode(ErrorCategory.SECURITY, 1, "AUTH_FAILED", "Authentication or authorization failed"),
        ErrorCode(ErrorCategory.DR, 1, "WAL_WRITE_FAILED", "WAL write operation failed"),
        ErrorCode(ErrorCategory.PROTOCOL, 1, "UNKNOWN_VERB", "Unrecognized message verb"),
    ]
    for ec in _standard:
        reg.register(ec)
    return reg


STANDARD_ERRORS: ErrorRegistry = _build_standard_errors()
