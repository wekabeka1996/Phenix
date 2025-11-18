"""Fail-closed behaviour tests for ExecPosFSM._execute_decision."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from vfoundation.core.fsm_emit_compat import Message

import apps.reference.domains.execution_position.fsm as execpos_mod


class DummyAdapter:
    def __init__(self):
        self.base_url = "https://testnet.binancefuture.com"

    async def cancel_order(self, *_: Any, **__: Any):
        return {"status": "CANCELLED"}

    async def get_open_positions(self, *_: Any, **__: Any):
        return [{"symbol": "SOLUSDT", "positionAmt": "1"}]


@pytest.fixture
def execpos_fsm(monkeypatch: pytest.MonkeyPatch) -> execpos_mod.ExecPosFSM:
    monkeypatch.setattr(
        execpos_mod.ExecPosFSM,
        "_schedule_fsm_cleanup_loop",
        lambda self: None,
    )
    monkeypatch.setattr(
        execpos_mod.ExecPosFSM,
        "_schedule_guardian_start",
        lambda self: None,
    )
    fsm = execpos_mod.ExecPosFSM(config={}, fsm=None)
    fsm.adapter = DummyAdapter()
    loop = asyncio.new_event_loop()
    monkeypatch.setattr(execpos_mod.asyncio, "get_running_loop", lambda: loop)
    return fsm


@pytest.mark.asyncio
async def test_execute_decision_missing_symbol_fail_closed(execpos_fsm: execpos_mod.ExecPosFSM, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("ERROR")
    msg = Message(op="DEC", verb="ADJUST", src="test",
                  dst="execution_position", rid="rid-1", pld={"foo": "bar"})

    await execpos_fsm._execute_decision(msg)

    assert any(
        "DECISION_MISSING_SYMBOL" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_execute_decision_exception_logged(execpos_fsm: execpos_mod.ExecPosFSM, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("ERROR")

    async def boom(*_: Any, **__: Any):  # noqa: ANN001
        raise RuntimeError("boom")

    # type: ignore[attr-defined]
    execpos_fsm.adapter.place_market_reduce_only = boom

    msg = Message(
        op="DEC",
        verb="CLOSE",
        src="test",
        dst="execution_position",
        rid="rid-2",
        pld={"symbol": "SOLUSDT", "side": "SELL", "qty": "1"},
    )

    await execpos_fsm._execute_decision(msg)

    assert any(
        "DECISION_EXECUTION_FAILED" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_execute_decision_qty_rounds_to_zero_logged(execpos_fsm: execpos_mod.ExecPosFSM, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")

    async def rounding_error(*_: Any, **__: Any):  # noqa: ANN001
        raise ValueError("Quantity rounds to zero with stepSize")

    # type: ignore[attr-defined]
    execpos_fsm.adapter.place_market_reduce_only = rounding_error

    msg = Message(
        op="DEC",
        verb="CLOSE",
        src="test",
        dst="execution_position",
        rid="rid-qty",
        pld={"symbol": "SOLUSDT", "side": "SELL", "qty": "1"},
    )

    await execpos_fsm._execute_decision(msg)

    assert any(
        record.message == "DECISION_SKIPPED_QTY_UNDER_MIN" for record in caplog.records
    )
