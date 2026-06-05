"""Shared identity helpers for judge shadow artifacts."""

from __future__ import annotations

from datetime import datetime, timezone


def build_cycle_key(
    verdict_scope: str,
    symbol: str,
    tf_sec: int,
    ts_ms: int,
) -> str:
    """Build the canonical cycle identity for one judge evaluation."""
    return f"{str(verdict_scope).upper()}:{symbol}:{int(tf_sec)}:{int(ts_ms)}"


def build_expert_cycle_key(
    *,
    entry_verdict: str | None,
    lifecycle_verdict: str | None,
    symbol: str,
    tf_sec: int,
    ts_ms: int,
) -> str:
    """Build a cycle key for ExpertOutput where scope is implicit."""
    if entry_verdict is not None:
        scope = "ENTRY"
    elif lifecycle_verdict is not None:
        scope = "LIFECYCLE"
    else:
        raise ValueError(
            "Cannot build expert cycle key without entry_verdict or lifecycle_verdict"
        )
    return build_cycle_key(scope, symbol, tf_sec, ts_ms)


def utc_day_from_ts_ms(ts_ms: int) -> str:
    """Return the UTC partition day for the authoritative record timestamp."""
    return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d"
    )
