import asyncio
import types

import pytest

from vfoundation.core.fsm_emit_compat import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM


class Bus:
    def listen(self, *args, **kwargs):
        pass

    async def emit(self, *args, **kwargs):
        pass


class StubAdapter:
    def __init__(self):
        self.cancel_calls = []
        self.close_calls = []

    async def cancel_order(self, symbol, order_id=None, client_order_id=None):
        self.cancel_calls.append((symbol, order_id or client_order_id))
        return {"symbol": symbol, "orderId": order_id or client_order_id}

    async def get_open_positions(self):
        # Return a single long position to be closed
        return [
            {
                "symbol": "ETHUSDT",
                "positionAmt": "0.5",
                "positionSide": "BOTH",
            }
        ]

    async def place_market_reduce_only(self, symbol, side, quantity, new_client_order_id=None):
        self.close_calls.append((symbol, side, quantity, new_client_order_id))
        return {
            "symbol": symbol,
            "side": side,
            "executedQty": quantity,
            "clientOrderId": new_client_order_id,
        }


@pytest.mark.asyncio
async def test_close_cancels_brackets_then_places_reduce_only():
    cfg = {"trading": {"execution": {"manage": {"brackets": {"sl": {"fixed_bps": 50}, "tp": {"fixed_bps": 100}}}}}}
    fsm = ExecPosFSM(config=cfg, fsm=Bus(), shadow_mode=True)
    # Inject stub adapter
    stub = StubAdapter()
    stub.base_url = "https://testnet.binancefuture.com"
    fsm.adapter = stub
    # Pre-populate bracket tracking for symbol
    fsm._symbol_brackets["ETHUSDT"] = {"sl_order_id": "sl123", "tp_order_id": "tp456"}

    # Issue DEC:CLOSE for ETHUSDT
    dec = Message(op="DEC", verb="CLOSE", src="t", dst="execution_position", rid="r1", pld={"symbol": "ETHUSDT"})
    await fsm._execute_decision(dec)

    # Both brackets must be cancelled
    assert ("ETHUSDT", "sl123") in stub.cancel_calls
    assert ("ETHUSDT", "tp456") in stub.cancel_calls
    # And a reduce-only close must be placed
    assert stub.close_calls, "Reduce-only close was not placed"
    sym, side, qty, _ = stub.close_calls[0]
    assert sym == "ETHUSDT"
    assert side in ("SELL", "BUY")
    assert float(qty) == pytest.approx(0.5)
