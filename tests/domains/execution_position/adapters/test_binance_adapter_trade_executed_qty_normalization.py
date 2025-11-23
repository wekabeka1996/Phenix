import pytest

from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
)


def test_trade_executed_qty_normalized_positive():
    adapter = BinanceExecutionAdapter(fsm=None, config={}, shadow_mode=True)

    order_data = {
        "s": "BNBUSDT",
        "S": "SELL",
        "q": "0.07",     # orig
        "l": "-0.07",    # last fill (signed from exchange)
        "z": "-0.07",    # cum filled (signed from exchange)
        "L": "836.65",
        "n": "0.0117",
    }

    payload = adapter._build_trade_executed_payload(
        order_data,
        client_order_id="test_client",
        exchange_order_id="12345",
        order_ref=None,
        event_ts=1234567890,
    )

    assert payload is not None
    assert payload["side"] == "sell"
    assert payload["quantity"] == "0.07"
    assert payload["qty"] == "0.07"
    assert payload["cum_qty"] == "0.07"
    assert payload["last_fill_qty"] == "0.07"
