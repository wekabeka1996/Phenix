from __future__ import annotations
from typing import Any, Dict, List, Union

SENSITIVE = {"secret", "api_key", "token", "password"}


def redact(obj: Dict[str, Any]) -> Dict[str, Any]:
    return {k: ("***" if k in SENSITIVE else v) for k, v in obj.items()}


def redact_deep(
    obj: Any,
    sensitive: set[str] | None = None,
    max_depth: int = 10,
    _depth: int = 0,
) -> Any:
    """
    Recursively redact sensitive keys in nested dicts/lists.

    Args:
        obj: The object to redact (dict, list, or scalar).
        sensitive: Set of key names to redact. Defaults to SENSITIVE.
        max_depth: Maximum recursion depth to prevent infinite loops.

    Returns:
        Redacted copy of the object.
    """
    if _depth >= max_depth:
        return obj

    keys = sensitive if sensitive is not None else SENSITIVE

    if isinstance(obj, dict):
        return {
            k: ("***" if k in keys else redact_deep(v, keys, max_depth, _depth + 1))
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [redact_deep(item, keys, max_depth, _depth + 1) for item in obj]
    else:
        return obj
