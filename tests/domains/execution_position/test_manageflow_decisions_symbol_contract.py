"""Contract tests ensuring ManageFlow DEC payloads always include symbol."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from vfoundation.core.fsm_emit_compat import Message

from apps.reference.domains.execution_position.fsm_manage import (
    ManageFlowFSM,
    ManageState,
)


class DummyConfig:
    """Minimal config stub with required manage config attributes."""

    class Manage:
        class Brackets:
            oco_emulation = True
            keep_single_bracket_set = True

        brackets = Brackets()

        class Trailing:
            enabled = False
            activation_profit_atr_k = 1.0
            cooldown_sec = 0
            step_bps = 10

        trailing = Trailing()

        class Emergency:
            enabled = False
            sl_bps = Decimal("50")

        emergency = Emergency()

    def __init__(self) -> None:
        self.manage = self.Manage()

    def get(self, *_: Any, **__: Any) -> Any:  # pragma: no cover - compatibility shim
        return self.manage


@pytest.fixture
def manage_fsm() -> ManageFlowFSM:
    cfg = DummyConfig()
    fsm = ManageFlowFSM(config=cfg, symbol="SOLUSDT", rid="test-rid")
    fsm.state = ManageState.TRACKING
    fsm.position_qty = Decimal("1.0")
    fsm.position_entry_price = Decimal("100")
    fsm.position_side = "SELL"
    fsm.symbol = "SOLUSDT"
    return fsm


def _make_evt(symbol: str = "SOLUSDT") -> Message:
    return Message(
        op="EVT",
        verb="MARKET_DATA",
        src="test",
        dst="execution_position",
        rid="evt-rid",
        pld={"symbol": symbol, "price": "105"},
    )


def test_emit_adjust_includes_symbol_and_qty(manage_fsm: ManageFlowFSM) -> None:
    msg = _make_evt()
    decision = manage_fsm._emit_adjust(msg, "TEST_REASON", {"rule": "trail"})

    assert decision.op == "DEC"
    assert decision.verb == "ADJUST"
    assert decision.pld["symbol"] == "SOLUSDT"
    assert decision.pld["side"] == "SELL"
    assert decision.pld["qty"] == "1.0"


def test_emit_close_includes_symbol(manage_fsm: ManageFlowFSM) -> None:
    msg = _make_evt()
    decision = manage_fsm._emit_close(msg, "TEST_CLOSE", {"extra": True})

    assert decision.op == "DEC"
    assert decision.verb == "CLOSE"
    assert decision.pld["symbol"] == "SOLUSDT"
    assert decision.pld["side"] == "SELL"
    assert decision.pld["reduce_only"] is True
