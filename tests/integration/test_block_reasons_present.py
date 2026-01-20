from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


class _Msg:
    def __init__(self, pld: dict):
        self.pld = pld


class _Bus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[_Msg], None]]] = {}
        self.emitted: list[tuple[str, dict]] = []

    def listen(self, event_name: str, handler: Callable[[_Msg], None]) -> None:
        self._listeners.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, payload: dict | None = None, **_: Any) -> None:
        pld = payload or {}
        self.emitted.append((event_name, pld))
        for handler in list(self._listeners.get(event_name, [])):
            handler(_Msg(pld))


def test_block_reason_readiness_present() -> None:
    """readiness=false => reason contains READINESS."""
    import pytest
    pytest.skip("T2B-03: on_features_calculated is now data-only. STRATEGY_DECISION_BLOCKED requires CMD:PROCESS_STRATEGY path.")


def test_block_reason_regime_mapping_none_present() -> None:
    """regime_mapping None => reason contains REGIME_MAPPING_NONE."""
    import pytest
    pytest.skip("T2B-02: MR on_tick is deprecated. STRATEGY_DECISION_BLOCKED requires on_bar path.")


def test_block_reason_spread_present() -> None:
    """spread gate => reason contains SPREAD."""
    import pytest
    pytest.skip("T2B-03: on_features_calculated is now data-only. STRATEGY_DECISION_BLOCKED requires CMD:PROCESS_STRATEGY path.")
