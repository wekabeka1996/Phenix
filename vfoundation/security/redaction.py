from __future__ import annotations
from typing import Any, Dict

SENSITIVE = {"secret", "api_key", "token", "password"}


def redact(obj: Dict[str, Any]) -> Dict[str, Any]:
    return {k: ("***" if k in SENSITIVE else v) for k, v in obj.items()}
