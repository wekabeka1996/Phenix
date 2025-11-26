from decimal import Decimal

from apps.reference.domains.execution_position.contracts import ExecutionRequest


def test_execution_request_model_dump_with_aliases() -> None:
    request = ExecutionRequest(
        symbol="SOLUSDT",
        side="buy",
        quantity="1.5",
        order_type="MARKET",
        time_in_force="GTC",
        stop_price="25.1",
        reduce_only=True,
        client_order_id="cid-123",
    )

    dumped = request.model_dump(by_alias=True, exclude_none=True)

    assert dumped["symbol"] == "SOLUSDT"
    assert dumped["side"] == "BUY"
    assert dumped["quantity"] == Decimal("1.5")
    assert dumped["order_type"] == "MARKET"
    assert dumped["tif"] == "GTC"
    assert dumped["stop_price"] == Decimal("25.1")
    assert dumped["reduce_only"] is True
    assert dumped["client_order_id"] == "cid-123"
