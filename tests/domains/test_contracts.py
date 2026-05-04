from apps.reference.domains.execution_position.contracts import validate_order_command


def test_validate_order_command_good_and_bad():
    good = {
        "symbol": "ETHUSDT",
        "side": "BUY",
        "qty": "1",
        "order_type": "LIMIT",
        "price": "20",
    }
    assert validate_order_command(good) is True

    bad = {"symbol": "ETHUSDT", "side": "BUY", "qty": "0.0001", "order_type": "MARKET"}
    # qty too small -> validate_order_command should return False
    assert validate_order_command(bad) is False
