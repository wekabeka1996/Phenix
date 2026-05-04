from audit_shadow import is_placeholder_value, is_useful_value


def test_unknown_placeholder_values_are_not_useful():
    assert is_placeholder_value("unknown") is True
    assert is_placeholder_value("UNKNOWN") is True
    assert is_placeholder_value("  unknown  ") is True
    assert is_placeholder_value("unknown_disappearance") is False

    assert is_useful_value("BTCUSDT") is True
    assert is_useful_value("unknown") is False
    assert is_useful_value("  unknown  ") is False
    assert is_useful_value(None) is False
