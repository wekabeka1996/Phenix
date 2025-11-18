from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.execution_position.qty_guard import (
    ExecutionQtyGuard,
    QtyGuardResult,
)


@pytest.fixture
def instrument_profile() -> dict:
    return {
        "step_size": "0.001",
        "min_qty": "0.001",
        "min_notional": "0.001",
        "source": "test_fixture",
    }


@pytest.fixture
def guard(instrument_profile: dict) -> ExecutionQtyGuard:
    return ExecutionQtyGuard(instrument_lookup=lambda symbol: instrument_profile)


def test_qty_guard_allows_valid_quantity(guard: ExecutionQtyGuard):
    result = guard.evaluate(symbol="SOLUSDT", qty="0.005", price="20")

    assert isinstance(result, QtyGuardResult)
    assert result.allowed
    assert result.qty_str() == "0.005"
    assert result.metadata["symbol"] == "SOLUSDT"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0.0054", "0.005"),
        (Decimal("0.0059"), "0.005"),
    ],
)
def test_qty_guard_rounds_down_to_step(guard: ExecutionQtyGuard, raw, expected):
    result = guard.evaluate(symbol="SOLUSDT", qty=raw, price="30")

    assert result.allowed
    assert result.qty_str() == expected


def test_qty_guard_blocks_rounding_to_zero(instrument_profile: dict):
    custom_profile = {
        **instrument_profile,
        "min_qty": "0.0001",
    }
    local_guard = ExecutionQtyGuard(
        instrument_lookup=lambda symbol: custom_profile)

    result = local_guard.evaluate(symbol="SOLUSDT", qty="0.00015", price="30")

    assert not result.allowed
    assert result.reason == "qty_rounds_to_zero"


def test_qty_guard_blocks_below_min_qty(guard: ExecutionQtyGuard):
    result = guard.evaluate(symbol="SOLUSDT", qty="0.0005", price="30")

    assert not result.allowed
    assert result.reason == "below_min_qty"


def test_qty_guard_records_notional_metadata(guard: ExecutionQtyGuard):
    result = guard.evaluate(symbol="SOLUSDT", qty="0.001", price="1.0")

    assert result.allowed
    assert result.metadata["notional"] == "0.001"


def test_qty_guard_invalidate_cache(guard: ExecutionQtyGuard):
    guard._profile_cache["SOLUSDT"] = {"cached": True}
    guard.invalidate("SOLUSDT")
    assert "SOLUSDT" not in guard._profile_cache


def test_qty_guard_to_decimal_errors():
    with pytest.raises(ValueError, match="cannot be None"):
        ExecutionQtyGuard._to_decimal(None, "field")

    with pytest.raises(ValueError, match="must be numeric"):
        ExecutionQtyGuard._to_decimal("invalid", "field")

    with pytest.raises(ValueError, match="Unsupported field type"):
        ExecutionQtyGuard._to_decimal([], "field")


def test_qty_guard_extract_value_nested():
    # Test nested dicts - simplified to match supported keys
    data = {"limits": {"min_qty": "0.1"}}
    assert ExecutionQtyGuard._extract_value(data, "min_qty") == "0.1"

    # Test nested objects
    class Nested:
        def __init__(self):
            self.min_qty = "0.2"

    class Container:
        def __init__(self):
            self.limits = Nested()

    obj = Container()
    assert ExecutionQtyGuard._extract_value(obj, "min_qty") == "0.2"

    # Test direct attribute
    obj.direct = "0.3"
    assert ExecutionQtyGuard._extract_value(obj, "direct") == "0.3"

    # Test missing
    assert ExecutionQtyGuard._extract_value(obj, "missing") is None

def test_qty_guard_round_to_step_zero_or_negative():
    assert ExecutionQtyGuard._round_to_step(Decimal("1.23"), Decimal("0")) == Decimal("1.23")
    assert ExecutionQtyGuard._round_to_step(Decimal("1.23"), Decimal("-1")) == Decimal("1.23")

def test_qty_guard_extract_decimal_defaults():
    assert ExecutionQtyGuard._extract_decimal({}, "missing", Decimal("1.0")) == Decimal("1.0")
    assert ExecutionQtyGuard._extract_decimal({"val": "invalid"}, "val", Decimal("1.0")) == Decimal("1.0")


def test_qty_guard_extract_str_defaults():
    assert ExecutionQtyGuard._extract_str({}, "missing", "default") == "default"


def test_qty_guard_evaluate_non_positive_qty(guard: ExecutionQtyGuard):
    result = guard.evaluate(symbol="SOLUSDT", qty="0")
    assert not result.allowed
    assert result.reason == "non_positive_qty"

    result = guard.evaluate(symbol="SOLUSDT", qty="-1")
    assert not result.allowed
    assert result.reason == "non_positive_qty"


def test_qty_guard_evaluate_below_min_notional(guard: ExecutionQtyGuard):
    # min_notional is 0.001
    # qty 0.001 * price 0.5 = 0.0005 < 0.001
    result = guard.evaluate(symbol="SOLUSDT", qty="0.001", price="0.5")
    assert not result.allowed
    assert result.reason == "below_min_notional"


def test_qty_guard_result_qty_str_none():
    res = QtyGuardResult(allowed=False, normalized_qty=None, raw_qty=Decimal("1"))
    assert res.qty_str() is None


def test_qty_guard_resolve_profile_fallback(guard: ExecutionQtyGuard):
    # Test fallback to config
    guard._instrument_lookup = None
    guard._config = MagicMock()
    guard._config.resolve_instrument_profile = MagicMock(return_value={"step_size": "1"})

    # We need to mock resolve_instrument_profile function imported in qty_guard
    with patch("apps.reference.domains.execution_position.qty_guard.resolve_instrument_profile") as mock_resolve:
        mock_resolve.return_value = {"step_size": "1"}
        profile = guard._resolve_instrument_profile("BTCUSDT")
        assert profile == {"step_size": "1"}


def test_qty_guard_resolve_profile_none(guard: ExecutionQtyGuard):
    guard._instrument_lookup = None
    guard._config = None
    assert guard._resolve_instrument_profile("BTCUSDT") is None


def test_qty_guard_extract_from_shadow_dict():
    class Shadow:
        def __init__(self):
            self.__dict__ = {"field": "value"}

    obj = Shadow()
    # Access via __dict__ fallback
    assert ExecutionQtyGuard._extract_from_nested_attrs(obj, "field") == "value"

def test_qty_guard_safe_getattr_exception():
    class PropertyError:
        @property
        def error(self):
            raise AttributeError("Boom")

    obj = PropertyError()
    assert ExecutionQtyGuard._safe_getattr(obj, "error") is None

def test_qty_guard_resolve_profile_exceptions(guard: ExecutionQtyGuard):
    # Mock lookup to raise exception
    guard._instrument_lookup = MagicMock(side_effect=Exception("Lookup Error"))
    guard._config = None

    assert guard._resolve_instrument_profile("BTCUSDT") is None

    # Mock config resolve to raise exception
    guard._instrument_lookup = None
    guard._config = MagicMock()
    guard._config.resolve_instrument_profile = MagicMock(side_effect=Exception("Config Error"))

    # We need to patch the imported function again
    with patch("apps.reference.domains.execution_position.qty_guard.resolve_instrument_profile") as mock_resolve:
        mock_resolve.side_effect = Exception("Config Error")
        assert guard._resolve_instrument_profile("BTCUSDT") is None
