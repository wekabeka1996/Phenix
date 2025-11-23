import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2


@pytest.mark.asyncio
async def test_apply_fill_accepts_negative_quantity_by_abs():
    runtime = ExecPosRuntimeV2(config={}, adapter=None, price_service=None)

    event = {
        "kind": "TRADE_EXECUTED",
        "symbol": "BNBUSDT",
        "payload": {
            "symbol": "BNBUSDT",
            "side": "SELL",
            "quantity": "-0.07",
            "price": "836.65",
            "ts": 1234567890,
        },
    }

    await runtime.handle(event)

    pos = runtime._positions_by_symbol.get("BNBUSDT")
    assert pos is not None
    assert abs(pos.qty) > 0
    assert pos.side in ("LONG", "SHORT")
