from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from vfoundation.core.protocol import Message

import pytest

from apps.reference.core.time import MockClock, reset_clock, set_clock
from apps.reference.domains.execution_position.flows.manage.manage_max_hold_close_bridge import (
    MANAGE_MAX_HOLD_CLOSE_TRIGGER,
)
from tests.harness.execpos_scenarios import feed_opened_position


@pytest.fixture
def mock_clock() -> MockClock:
    clock = MockClock(start_ms=1_000_000)
    set_clock(clock)
    yield clock
    reset_clock()


def test_execpos_max_hold_close_is_executed_in_shadow_mode(fsm_harness, mock_clock):
    fsm, _bus, _cfg = fsm_harness

    fsm.adapter = MagicMock()
    fsm.shadow_mode = True

    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    manage.position_open_ts = mock_clock.now_sec()

    with patch.object(manage, "_get_max_hold_sec", return_value=1):
        mock_clock.set_time_ms(1_002_000)
        msg = Message(
            op="UPD",
            verb="MARKET_DATA",
            src="ws",
            dst="exec",
            pld={"symbol": "BTCUSDT", "last_price": "50000", "ts": 1_002_000},
        )
        with patch.object(fsm, "_get_async_loop", return_value=object()):
            with patch.object(fsm, "_submit_async") as submit:
                res = fsm.handle(msg)

    assert res is not None
    assert res.op == "DEC"
    assert res.verb == "CLOSE"
    assert res.pld["trigger"] == MANAGE_MAX_HOLD_CLOSE_TRIGGER
    assert res.pld["idempotent_key"] == "manage_max_hold:BTCUSDT:1000000:1.0:1"
    submit.assert_called_once()
