"""Unit tests for ExecutionQtyGuard min step/min notional logic (OCO-11.11)."""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Dict

import pytest

from apps.reference.domains.execution_position.qty_guard import (
    ExecutionQtyGuard,
    QtyGuardResult,
)


@pytest.fixture
def guard_factory() -> Callable[[Dict[str, str]], ExecutionQtyGuard]:
    def _factory(overrides: Dict[str, str] | None = None) -> ExecutionQtyGuard:
        profile = {
            "step_size": "0.01",
            "min_qty": "0.01",
            "min_notional": "5",
            "source": "unit_test",
        }
        if overrides:
            profile.update(overrides)
        return ExecutionQtyGuard(instrument_lookup=lambda symbol: profile)

    return _factory


def test_guard_rounds_down_and_allows_qty(guard_factory: Callable[[Dict[str, str]], ExecutionQtyGuard]) -> None:
    guard = guard_factory({"min_notional": "1"})

    result = guard.evaluate(
        symbol="SOLUSDT", qty=Decimal("0.1234"), price="200")

    assert isinstance(result, QtyGuardResult)
    assert result.allowed is True
    assert result.qty_str() == "0.12"


def test_guard_blocks_rounding_to_zero_when_step_bigger_than_qty(
    guard_factory: Callable[[Dict[str, str]], ExecutionQtyGuard]
) -> None:
    guard = guard_factory({"min_qty": "0.0001"})

    result = guard.evaluate(symbol="SOLUSDT", qty="0.0009", price="50")

    assert result.allowed is False
    assert result.reason == "qty_rounds_to_zero"


def test_guard_blocks_below_min_notional(
    guard_factory: Callable[[Dict[str, str]], ExecutionQtyGuard]
) -> None:
    guard = guard_factory({"min_notional": "25"})

    result = guard.evaluate(symbol="SOLUSDT", qty="0.02", price="500")

    assert result.allowed is False
    assert result.reason == "below_min_notional"
    assert result.metadata["violation"] == "below_min_notional"
    assert result.metadata["notional"] == "10"
