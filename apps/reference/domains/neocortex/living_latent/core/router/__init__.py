"""Stub Router module.

Provides a minimal Router class so that optional imports in run_r0.py
do not raise ImportError when the full R2 router implementation is
absent. This keeps Pylance and static analysis quiet while preserving
the try/except guard semantics (real implementations can override by
placing a proper module earlier on sys.path).
"""
from __future__ import annotations
from typing import Any, Sequence

class Router:
    """Minimal no-op Router.

    The real Router would score/select among attractors or bridges.
    This stub simply returns the first candidate (if any) and a small
    metadata dict indicating it is a stub so downstream code can detect
    degraded mode if needed.
    """

    def __init__(self, cfg: dict | None = None, emit=None):  # type: ignore[annotation-unchecked]
        self.cfg = cfg or {}
        self.emit = emit

    def choose(self, candidates: Sequence[Any] | None, ctx: Any | None = None):  # noqa: D401
        """Return (selected, meta).

        selected: first element of candidates or None.
        meta: {'stub': True, 'count': <len>} so callers can branch.
        """
        if candidates:
            selected = candidates[0]
        else:
            selected = None
        meta = {"stub": True, "count": len(candidates) if candidates else 0}
        if self.emit:
            try:
                self.emit({"event": "r2_router_stub_choose", "meta": meta})
            except Exception:
                pass
        return selected

__all__ = ["Router"]
