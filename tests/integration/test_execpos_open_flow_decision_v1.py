from decimal import Decimal
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message


pytest_plugins = ("tests.domains.execution_position.conftest",)


def test_execpos_cmd_open_produces_dec_open_when_exposure_allows(fsm_harness):
    fsm, _bus, cfg = fsm_harness

    # Ensure exposure can_open allows.
    fsm.exposure_guard._latest_portfolio_state = {
        "positions_last_ts_ms": 9999999999999,
        "equity_free_usdt": "10000",
        "open_positions_margin_usd": "0",
        "positions": [],
    }

    # Make sure leverage defaults exist for reserve/can_open path.
    cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20, "BTCUSDT": 20}

    # CMD:OPEN needs to pass OpenFlowFSM guards: qty >= min_qty, notional >= min_notional
    msg = Message(
        op="CMD",
        verb="OPEN",
        src="bridge",
        dst="execution_position",
        rid="RID-INTEG-OPEN-1",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": str(Decimal("0.01")),
            "price": str(Decimal("1000")),
            "order_type": "LIMIT",
            "tif": "GTC",
            "valid_for_ms": 60_000,
            "idempotent_key": "K-INTEG-OPEN-1",
        },
    )

    out = fsm.handle(msg)
    assert out is not None
    assert out.op == "DEC" and out.verb == "OPEN"
    assert out.pld["symbol"] == "BTCUSDT"
    assert out.pld["side"] == "BUY"
    assert Decimal(out.pld["qty"]) > 0
    assert Decimal(out.pld["price"]) > 0
