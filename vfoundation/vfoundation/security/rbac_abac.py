from __future__ import annotations
from typing import Optional


def require_admin(auth_header: Optional[str]) -> bool:
    # Lazy import to support test ENV changes
    from ..config import config

    if not auth_header:
        return False
    token = auth_header.replace("Bearer ", "")
    return token in config.rbac_admin_tokens
