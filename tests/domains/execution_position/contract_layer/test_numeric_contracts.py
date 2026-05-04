from decimal import Decimal

import pytest

from apps.reference.domains.execution_position import contracts as legacy_contracts
from apps.reference.domains.execution_position.contract_layer import numeric


def test_numeric_constants_match_legacy_contracts() -> None:
    assert numeric.MIN_ORDER_QTY == legacy_contracts.MIN_ORDER_QTY
    assert numeric.MAX_ORDER_QTY == legacy_contracts.MAX_ORDER_QTY
    assert numeric.MIN_PRICE == legacy_contracts.MIN_PRICE
    assert numeric.MAX_PRICE == legacy_contracts.MAX_PRICE
    assert numeric.MIN_NOTIONAL == legacy_contracts.MIN_NOTIONAL
    assert numeric.QTY_STEP == legacy_contracts.QTY_STEP
    assert numeric.PRICE_STEP == legacy_contracts.PRICE_STEP


def test_validate_qty_quantizes_with_current_contract_step() -> None:
    assert numeric.validate_qty("1.5555") == Decimal("1.555")


def test_validate_qty_rejects_out_of_bounds_values() -> None:
    with pytest.raises(ValueError, match="qty must be >="):
        numeric.validate_qty("0.0001")

    with pytest.raises(ValueError, match="qty must be <="):
        numeric.validate_qty("1001")


def test_validate_price_quantizes_with_current_contract_step() -> None:
    assert numeric.validate_price("50000.999") == Decimal("50000.99")


def test_validate_price_rejects_out_of_bounds_values() -> None:
    with pytest.raises(ValueError, match="price must be >="):
        numeric.validate_price("0.001")

    with pytest.raises(ValueError, match="price must be <="):
        numeric.validate_price("1000000.01")


def test_parse_decimal_keeps_legacy_error_contract() -> None:
    with pytest.raises(ValueError, match="qty must be valid number"):
        numeric.parse_decimal("not-a-number", field_name="qty")
