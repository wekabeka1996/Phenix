from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.reference.domains.execution_position.contracts import TradeIntentPayload


def test_trade_intent_payload_accepts_canonical_fields() -> None:
    payload = TradeIntentPayload(
        symbol="BTCUSDT",
        side="buy",
        quantity="0.1",
        price="25000.5",
        order_type="LIMIT",
        time_in_force="GTC",
        idempotent_key="idem-1",
    )

    assert payload.symbol == "BTCUSDT"
    assert payload.side == "BUY"
    assert payload.quantity == Decimal("0.1")
    assert payload.price == Decimal("25000.5")
    assert payload.time_in_force == "GTC"
    assert payload.idempotent_key == "idem-1"


def test_trade_intent_payload_missing_symbol_raises() -> None:
    with pytest.raises(ValidationError):
        TradeIntentPayload(
            symbol=None,
            side="SELL",
            quantity="1",
        )


def test_trade_intent_payload_accepts_qty_alias() -> None:
    payload = TradeIntentPayload.model_validate(
        {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "qty": "0.25",
            "price_ref": "1600",
            "order_type": "MARKET",
        }
    )

    assert payload.symbol == "ETHUSDT"
    assert payload.quantity == Decimal("0.25")
    assert payload.price_ref == Decimal("1600")
