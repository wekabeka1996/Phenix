from decimal import Decimal

from apps.reference.domains.execution_position.contracts import OpenCommandPayload


def test_open_command_payload_dump_uses_aliases() -> None:
    payload = OpenCommandPayload(
        symbol="ETHUSDT",
        side="sell",
        quantity="2",
        price="1000.01",
        order_type="LIMIT",
        time_in_force="IOC",
        rid="rid-123",
        idempotent_key="id-1",
    )

    dumped = payload.model_dump(by_alias=True, exclude_none=True)

    assert dumped["qty"] == Decimal("2")
    assert dumped["symbol"] == "ETHUSDT"
    assert dumped["order_type"] == "LIMIT"
    assert dumped["tif"] == "IOC"
    assert "quantity" not in dumped
    assert dumped["rid"] == "rid-123"
