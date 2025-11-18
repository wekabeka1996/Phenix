import pytest
from decimal import Decimal
from apps.reference.domains.execution_position.contracts import (
    PositionSide,
    canonicalize_position_side,
    canonicalize_position_side_from_qty,
)

def test_position_side_enum():
    assert PositionSide.LONG == "LONG"
    assert PositionSide.SHORT == "SHORT"
    assert PositionSide.FLAT == "FLAT"

def test_canonicalize_position_side():
    assert canonicalize_position_side("LONG") == PositionSide.LONG
    assert canonicalize_position_side("long") == PositionSide.LONG
    assert canonicalize_position_side("BUY") == PositionSide.LONG
    assert canonicalize_position_side("buy") == PositionSide.LONG

    assert canonicalize_position_side("SHORT") == PositionSide.SHORT
    assert canonicalize_position_side("short") == PositionSide.SHORT
    assert canonicalize_position_side("SELL") == PositionSide.SHORT
    assert canonicalize_position_side("sell") == PositionSide.SHORT

    assert canonicalize_position_side("FLAT") == PositionSide.FLAT
    assert canonicalize_position_side("flat") == PositionSide.FLAT

    assert canonicalize_position_side(None) is None
    assert canonicalize_position_side("") is None
    assert canonicalize_position_side("UNKNOWN") is None

def test_canonicalize_position_side_from_qty():
    assert canonicalize_position_side_from_qty(Decimal("1.0")) == PositionSide.LONG
    assert canonicalize_position_side_from_qty(Decimal("0.001")) == PositionSide.LONG

    assert canonicalize_position_side_from_qty(Decimal("-1.0")) == PositionSide.SHORT
    assert canonicalize_position_side_from_qty(Decimal("-0.001")) == PositionSide.SHORT

    assert canonicalize_position_side_from_qty(Decimal("0")) == PositionSide.FLAT
    assert canonicalize_position_side_from_qty(Decimal("0.0")) == PositionSide.FLAT
    assert canonicalize_position_side_from_qty(None) == PositionSide.FLAT

    # Test with strings/floats if the function handles them (it converts to Decimal)
    assert canonicalize_position_side_from_qty("10") == PositionSide.LONG
    assert canonicalize_position_side_from_qty("-10") == PositionSide.SHORT
