from __future__ import annotations

from decimal import Decimal
from typing import Any


def _coerce_positive_decimal(value: Any) -> Decimal:
    """Coerce numeric config values to positive Decimal (accepts numeric strings)."""
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError("decimal value must not be empty")
        try:
            dec = Decimal(raw)
        except Exception as exc:
            raise ValueError(f"invalid decimal value: {value!r}") from exc
    elif isinstance(value, (int, float)):
        try:
            dec = Decimal(str(value))
        except Exception as exc:
            raise ValueError(f"invalid decimal value: {value!r}") from exc
    else:
        raise ValueError(
            f"unsupported decimal value type: {type(value).__name__}")

    if dec <= 0:
        raise ValueError(f"decimal value must be > 0, got {dec}")
    return dec


__all__ = ["_coerce_positive_decimal"]
