"""
Deprecation Policy Validator — Phase 16.4.

Centralized deprecation tracking and enforcement per Constitution §10.4.
Provides a registry for deprecated APIs/features and a decorator
to automatically emit DeprecationWarnings.
"""
from __future__ import annotations

import functools
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class DeprecationEntry:
    """Track a deprecated API/feature."""
    name: str
    deprecated_since: str              # version or ISO date
    removal_target: str                # version or ISO date
    replacement: Optional[str] = None  # suggested replacement
    reason: Optional[str] = None       # why deprecated


class DeprecationRegistry:
    """
    Centralized deprecation tracking.

    Constitution §10.4 requires deprecation windows minimum 2 releases.
    This registry ensures all deprecations are documented, queryable,
    and consistently enforced.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, DeprecationEntry] = {}

    def register(self, entry: DeprecationEntry) -> None:
        """Register a deprecation entry."""
        self._entries[entry.name] = entry

    def get(self, name: str) -> Optional[DeprecationEntry]:
        """Get deprecation entry by name. Returns None if not deprecated."""
        return self._entries.get(name)

    def is_deprecated(self, name: str) -> bool:
        """Check if a name is registered as deprecated."""
        return name in self._entries

    def warn_if_deprecated(self, name: str) -> None:
        """Emit DeprecationWarning if name is deprecated. No-op otherwise."""
        entry = self._entries.get(name)
        if entry is None:
            return
        msg = f"{entry.name} deprecated since {entry.deprecated_since}"
        if entry.replacement:
            msg += f". Use {entry.replacement} instead"
        msg += f". Removal target: {entry.removal_target}"
        warnings.warn(msg, DeprecationWarning, stacklevel=2)

    def all_entries(self) -> List[DeprecationEntry]:
        """Return all registered deprecation entries."""
        return list(self._entries.values())


def deprecated(
    name: str,
    since: str,
    removal: str,
    replacement: Optional[str] = None,
) -> Callable[[F], F]:
    """
    Decorator to mark a function/method as deprecated.

    Emits DeprecationWarning on every call with structured message.

    Args:
        name: Human-readable name for the deprecated feature.
        since: Version or date when deprecation started.
        removal: Version or date when removal is planned.
        replacement: Optional replacement suggestion.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            msg = f"{name} deprecated since {since}, removal target {removal}"
            if replacement:
                msg += f". Use {replacement} instead"
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)
        return wrapper  # type: ignore[return-value]
    return decorator
