from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from vfoundation.core.protocol import Message

from tests.harness.execpos_scenarios import feed_opened_position


def test_execpos_max_hold_close_is_executed_in_shadow_mode(fsm_harness):
    fsm, _bus, _cfg = fsm_harness

    fsm.adapter = MagicMock()
    fsm.shadow_mode = True

    feed_opened_position(fsm, "BTCUSDT", "BUY", Decimal("1.0"), Decimal("50000"))
    manage = fsm.manage_flows["BTCUSDT"]
    manage.position_open_ts = 1000.0

    with patch.object(manage, "_get_max_hold_sec", return_value=1):
        with patch("apps.reference.domains.execution_position.fsm_manage.time.time", return_value=1002.0):
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
    submit.assert_called_once()

