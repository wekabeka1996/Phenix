from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

T = TypeVar("T")


def dget(mapping: Mapping[str, T], key: str, default: T) -> T:
    if key in mapping:
        return mapping[key]
    return default


def aget(obj: Any, name: str, default: T) -> T:
    if hasattr(obj, name):
        return getattr(obj, name)
    return default

