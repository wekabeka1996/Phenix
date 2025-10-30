from __future__ import annotations
from typing import Optional
import uuid


def new_span(parent: Optional[str] = None) -> tuple[str, Optional[str]]:
    return (uuid.uuid4().hex, parent)
