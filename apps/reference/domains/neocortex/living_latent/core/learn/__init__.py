"""Stub OffPolicyLearner module.

Supplies a minimal OffPolicyLearner used only to satisfy optional
imports in orchestrator scripts. The stub tracks a simple in-memory
replay list of bridge evaluation dictionaries and exposes train_epoch
that performs a no-op while returning a dummy metrics dict.
"""
from __future__ import annotations
from typing import Any, Iterable

class OffPolicyLearner:
    def __init__(self, cfg: dict | None = None):  # type: ignore[annotation-unchecked]
        self.cfg = cfg or {}
        self.replay = type("_Replay", (), {"buf": []})()

    def ingest_from_bridges(self, bridges: Iterable[Any] | None):  # noqa: D401
        if not bridges:
            return
        for b in bridges:
            try:
                self.replay.buf.append(b)
            except Exception:
                break

    def train_epoch(self) -> dict:
        """Simulate one training epoch and return dummy metrics."""
        # Real implementation would sample from replay and update models.
        return {"stub": True, "replay_size": len(self.replay.buf)}

__all__ = ["OffPolicyLearner"]
