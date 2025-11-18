"""Tests for execution_position position side helpers."""

from decimal import Decimal

from apps.reference.domains.execution_position.contracts import (
    PositionSide,
    canonicalize_position_side,
    canonicalize_position_side_from_qty,
)


def test_canonicalize_position_side_from_qty_handles_signs_and_flat():
    assert canonicalize_position_side_from_qty(
        Decimal("1.25")) == PositionSide.LONG
    assert canonicalize_position_side_from_qty(
        Decimal("-0.5")) == PositionSide.SHORT
    assert canonicalize_position_side_from_qty(
        Decimal("0")) == PositionSide.FLAT
    assert canonicalize_position_side_from_qty(None) == PositionSide.FLAT


def test_canonicalize_position_side_accepts_flat_string():
    assert canonicalize_position_side("flat") == PositionSide.FLAT
    assert canonicalize_position_side("FLAT") == PositionSide.FLAT
