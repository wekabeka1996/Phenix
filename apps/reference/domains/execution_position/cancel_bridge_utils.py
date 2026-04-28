"""Low-level helpers shared by explicit cancel bridge modules.

These helpers intentionally stay below bridge semantics. Callers still own
their exception type, message prefix, trace-ref params, and payload assembly.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode


def clean_required_str(
    value: Any,
    *,
    field_name: str,
    message_prefix: str,
    error_factory: Callable[[str], Exception] | None = None,
    error_type: type[Exception] | None = None,
) -> str:
    """Return stripped text or raise the caller-owned exception."""
    if error_factory is not None and error_type is not None:
        raise TypeError("pass error_factory or error_type, not both")
    if error_factory is None:
        if error_type is None:
            raise TypeError("missing error_factory or error_type")
        error_factory = error_type

    cleaned = str(value or "").strip()
    if not cleaned:
        raise error_factory(
            f"{message_prefix} missing required field: {field_name}")
    return cleaned


def build_trace_ref(*, prefix: str, params: Mapping[str, Any]) -> str:
    """Join a caller-owned trace prefix with caller-owned query params."""
    return f"{prefix}{urlencode(params)}"
