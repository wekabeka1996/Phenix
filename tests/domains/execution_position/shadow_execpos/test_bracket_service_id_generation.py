"""
Tests for BracketService ID Generation Logic
============================================

Verifies deterministic clientOrderId generation and parsing logic moved from Runtime.
"""
from decimal import Decimal
import pytest
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    make_bracket_client_order_id,
    build_position_id,
    parse_cycle_id_from_client_order_id,
    PositionView
)

def test_build_position_id_deterministic():
    """Test that position ID is deterministic based on qty and price."""
    pos = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.23456789"),
        avg_entry_price=Decimal("50000.50"),
        cycle_id=10
    )

    # Should format as "{qty:.4f}-{price:.2f}"
    # 1.2346 (rounded) - 50000.50
    pid = build_position_id("BTCUSDT", pos)
    assert pid == "1.2346-50000.50"

def test_parse_cycle_id_from_client_order_id():
    """Test parsing cycle ID from various client order ID formats."""
    # Standard format
    assert parse_cycle_id_from_client_order_id("AUR-BTC-LONG-SL-C123-FP") == 123

    # End of string
    assert parse_cycle_id_from_client_order_id("AUR-BTC-LONG-SL-C456") == 456

    # Legacy/Missing
    assert parse_cycle_id_from_client_order_id("AUR-BTC-LONG-SL-FP") == 0
    assert parse_cycle_id_from_client_order_id("") == 0
    assert parse_cycle_id_from_client_order_id(None) == 0

def test_make_bracket_client_order_id_format_fits():
    """Test standard bracket client order ID generation where it fits."""
    # Short symbol to ensure it fits in 32 chars
    # AUR-BTC-SHORT-PLACE_SL-C5- = 26 chars
    # Leaves 6 chars for pos ID
    pos = PositionView(
        symbol="BTC",
        side="SHORT",
        qty=Decimal("10.0"),
        avg_entry_price=Decimal("2000.0"),
        cycle_id=5
    )

    cid = make_bracket_client_order_id(
        symbol="BTC",
        action_type="PLACE_SL",
        exit_side="BUY",
        qty=10.0,
        price=Decimal("2100.0"),
        position=pos
    )

    # Expected: AUR-BTC-SHORT-PLACE_SL-C5-10.0000-2000.00 (truncated)
    # Prefix: AUR-BTC-SHORT-PLACE_SL-C5- (26 chars)
    # PosID: 10.0000-2000.00
    # Remaining: 6 chars -> "10.000"
    assert cid.startswith("AUR-BTC-SHORT-PLACE_SL-C5-")
    assert len(cid) <= 32
    # Verify we got at least part of the position ID
    assert cid.endswith("10.000")

def test_make_bracket_client_order_id_truncation_behavior():
    """Test that client order ID is truncated correctly when it overflows."""
    # Long symbol
    symbol = "VERYLONGSYMBOL"
    pos = PositionView(
        symbol=symbol,
        side="LONG",
        qty=Decimal("12345.6789"),
        avg_entry_price=Decimal("98765.43"),
        cycle_id=999
    )

    cid = make_bracket_client_order_id(
        symbol=symbol,
        action_type="PLACE_TP",
        exit_side="SELL",
        qty=12345.6789,
        price=Decimal("100000.0"),
        position=pos
    )

    assert len(cid) <= 32
    # In this extreme case, even the cycle ID might be cut if the prefix is too long
    # AUR-VERYLONGSYMBOL-LONG-PLACE_TP (32 chars exactly)
    # So we expect it to be exactly that
    expected_prefix = "AUR-VERYLONGSYMBOL-LONG-PLACE_TP"
    assert cid.startswith(expected_prefix[:32])

def test_make_bracket_client_order_id_fallback():
    """Test fallback generation when no position is provided (legacy/recovery)."""
    cid = make_bracket_client_order_id(
        symbol="BTCUSDT",
        action_type="PLACE_SL",
        exit_side="SELL",
        qty=0.5,
        price=Decimal("29000.0"),
        position=None
    )

    assert cid.startswith("AUR-BRK-")
    assert len(cid) <= 32
