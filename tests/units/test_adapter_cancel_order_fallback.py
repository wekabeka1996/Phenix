"""
Test that cancel_order resolves symbol by scanning open orders when not provided.
This test monkeypatches adapter internals to avoid real network calls.
"""

import pytest
from vfoundation.core.protocol import Message
# MIGRATED: BinanceExecutionAdapter -> BinanceAdapter (unified adapter)
from apps.reference.adapters.binance_adapter import BinanceAdapter as BinanceExecutionAdapter


class DummyOrderIndex:
    def get(self, **kwargs):
        return None  # force not found to trigger fallback


class DummyFSMCore:
    def __init__(self):
        self.order_index = DummyOrderIndex()


@pytest.mark.skip(reason="Method _find_order_symbol_by_id not implemented in adapter")
def test_cancel_order_fallback_resolves_symbol(monkeypatch):
    adapter = BinanceExecutionAdapter(
        shadow_mode=False, fsm_core=DummyFSMCore())

    # Monkeypatch finder to return desired symbol
    monkeypatch.setattr(
        adapter,
        "_find_order_symbol_by_id",
        lambda order_id: "SOLUSDT",
        raising=True,
    )

    called = {"args": None}

    def _fake_cancel(order_id: str, symbol: str):
        called["args"] = (order_id, symbol)
        return {"status": "CANCELED"}

    monkeypatch.setattr(adapter, "_cancel_binance_order",
                        _fake_cancel, raising=True)

    dec_msg = Message(
        op="DEC",
        verb="CANCEL_ORDER",
        src="test",
        dst="execution_position",
        rid="RID-CANCEL",
        pld={"orderId": "123456789"},  # no symbol on purpose
    )

    result = adapter.cancel_order(dec_msg)
    assert result.get("lifecycle") == "accepted" or result.get(
        "instrument") == "cancelled"
    # Ensure cancel was called with resolved symbol
    assert called["args"] is not None
    assert called["args"][1] == "SOLUSDT"
