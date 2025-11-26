from decimal import Decimal

from apps.reference.domains.execution_position.contracts import resolve_order_defaults


def test_default_market_when_no_price() -> None:
    order_type, tif = resolve_order_defaults(price=None, order_type=None, time_in_force=None)
    assert order_type == "MARKET"
    assert tif is None


def test_default_limit_with_price_sets_gtc() -> None:
    order_type, tif = resolve_order_defaults(price=Decimal("100"), order_type=None, time_in_force=None)
    assert order_type == "LIMIT"
    assert tif == "GTC"


def test_limit_without_tif_sets_gtc() -> None:
    order_type, tif = resolve_order_defaults(price=Decimal("100"), order_type="LIMIT", time_in_force=None)
    assert order_type == "LIMIT"
    assert tif == "GTC"


def test_explicit_order_type_preserved() -> None:
    order_type, tif = resolve_order_defaults(price=Decimal("100"), order_type="STOP_MARKET", time_in_force="IOC")
    assert order_type == "STOP_MARKET"
    assert tif == "IOC"
