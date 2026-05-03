"""Approximate token budgeting helpers for context assembly."""
from __future__ import annotations


def estimate_tokens(text: str, approximate_token_ratio: int = 4) -> int:
    if approximate_token_ratio <= 0:
        raise ValueError("approximate_token_ratio must be > 0")
    return max(1, len(text) // approximate_token_ratio) if text else 0


def truncate_chars(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."
