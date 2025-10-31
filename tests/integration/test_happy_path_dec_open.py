from decimal import Decimal
from vfoundation.core.protocol import Message
from vfoundation.apps.reference.domains.execution_position.fsm_open import OpenFlowFSM
from vfoundation.apps.reference.domains.execution_position.exposure_guard import ExposureGuard


def test_happy_path_dec_open_monolithic():
    # Clean config: instruments and exposure wide open
    config = {
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "min_qty": 0.001,
                    "step_size": 0.001,
                    "tick_size": 0.01,
                    "min_notional": 10,
                }
            }
        }
    }

    exposure_cfg = {"exposure": {"max_portfolio_fraction": 1.0, "pending_reservation_ttl_sec": 5}}
    eg = ExposureGuard(exposure_cfg)
    # set equity high enough
    eg.state.equity_free_usdt = Decimal("5000")
    eg.state.open_positions_usd = Decimal("0")

    fsm = OpenFlowFSM(cooldown_sec=0, guard_enabled=True, config=config, exposure_guard=eg)

    # Create CMD:OPEN message (market order with price_ref)
    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": 0.01,
            "order_type": "MARKET",
            "price_ref": 2000,
            "idempotent_key": "test-happy-1",
        },
    )

    dec = fsm.handle(msg)
    assert dec is not None, "Expected DEC:OPEN but got None"
    assert dec.op == "DEC" and dec.verb == "OPEN"
    # why should indicate success
    assert getattr(dec, "why", None) == "OPEN_OK"
    # payload should contain idempotent_key passed-through
    assert dec.pld.get("idempotent_key") == "test-happy-1"
    # qty must be string in DEC payload
    assert isinstance(dec.pld.get("qty"), str)
