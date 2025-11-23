"""
Tests for ExecPosGatekeeper Ported Guard Logic
==============================================

Tests entry validation ported from fsm_open.py and qty_guard.py.
"""
import pytest
import time
from decimal import Decimal

from apps.reference.domains.execution_position.shadow_execpos.gatekeeper import ExecPosGatekeeper

@pytest.fixture
def gatekeeper():
    return ExecPosGatekeeper(config={"cooldown_sec": 0.5})

# --- VALID ENTRY ---

def test_valid_entry_passes_all_guards(gatekeeper):
    """Test entry that passes all validation guards."""
    decision = gatekeeper.check_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.1",
        price="50000",
        order_type="LIMIT"
    )
    
    assert decision["allowed"] is True
    assert decision["reason"] == "OK"
    assert "quantity" in decision["modified_params"]

# --- NON-POSITIVE QTY ---

def test_non_positive_quantity_rejected(gatekeeper):
    """Test that qty <= 0 is rejected."""
    decision = gatekeeper.check_entry(
        symbol="ETHUSDT",
        side="SELL",
        quantity="0",
        price="3000",
        order_type="LIMIT"
    )
    
    assert decision["allowed"] is False
    assert decision["reason"] == "NON_POSITIVE_QTY"

def test_negative_quantity_rejected(gatekeeper):
    """Test that negative qty is rejected."""
    decision = gatekeeper.check_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity="-0.5",
        price="50000",
        order_type="LIMIT"
    )
    
    assert decision["allowed"] is False
    assert decision["reason"] == "NON_POSITIVE_QTY"

# --- MIN_QTY VIOLATION ---

def test_below_min_qty_rejected(gatekeeper):
    """Test qty below minimum is rejected."""
    # Default min_qty is 0.000001
    decision = gatekeeper.check_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.0000001",  # Below min
        price="50000",
        order_type="LIMIT"
    )
    
    assert decision["allowed"] is False
    assert decision["reason"] == "MIN_QTY_VIOLATION"

# --- ROUNDING ---

def test_quantity_rounding_to_step_size(gatekeeper):
    """Test quantity is rounded to step size."""
    # Input: 0.1234567 (7 decimals)
    # Step size: 0.000001 (6 decimals)
    # Expected: 0.123456 (rounded DOWN)
    decision = gatekeeper.check_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.1234567",
        price="50000",
        order_type="LIMIT"
    )
    
    assert decision["allowed"] is True
    adjusted_qty = Decimal(decision["modified_params"]["quantity"])
    assert adjusted_qty == Decimal("0.123456")

def test_qty_rounds_to_zero_rejected(gatekeeper):
    """Test very small qty that rounds to zero is rejected."""
    # Step size is 0.000001, so anything < 0.0000005 rounds to 0
    decision = gatekeeper.check_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.00000001",
        price="50000",
        order_type="LIMIT"
    )
    
    assert decision["allowed"] is False
    # With default min_qty=1e-6, this fails min_qty check first
    assert decision["reason"] in ["MIN_QTY_VIOLATION", "QTY_ROUNDS_TO_ZERO"]

# --- MIN_NOTIONAL VIOLATION ---

def test_below_min_notional_rejected(gatekeeper):
    """Test notional (qty * price) below minimum is rejected."""
    # Default min_notional = 5
    # qty=0.0001, price=1000 → notional=0.1 < 5
    decision = gatekeeper.check_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.0001",
        price="1000",
        order_type="LIMIT"
    )
    
    assert decision["allowed"] is False
    assert decision["reason"] == "MIN_NOTIONAL_VIOLATION"

def test_min_notional_passes(gatekeeper):
    """Test notional above minimum passes."""
    # qty=0.001, price=50000 → notional=50 > 5
    decision = gatekeeper.check_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.001",
        price="50000",
        order_type="LIMIT"
    )
    
    assert decision["allowed"] is True

# --- COOLDOWN ---

def test_cooldown_rejects_rapid_entry(gatekeeper):
    """Test that entries within cooldown window are rejected."""
    # First entry
    decision1 = gatekeeper.check_entry(
        symbol="ETHUSDT",
        side="BUY",
        quantity="1.0",
        price="3000",
        order_type="LIMIT"
    )
    assert decision1["allowed"] is True
    
    # Immediate second entry (within cooldown)
    decision2 = gatekeeper.check_entry(
        symbol="ETHUSDT",
        side="BUY",
        quantity="1.0",
        price="3000",
        order_type="LIMIT"
    )
    assert decision2["allowed"] is False
    assert decision2["reason"] == "COOLDOWN_ACTIVE"

def test_cooldown_allows_after_elapsed(gatekeeper):
    """Test that entry is allowed after cooldown elapses."""
    # Configured cooldown is 0.5 seconds
    # First entry
    decision1 = gatekeeper.check_entry(
        symbol="SOLUSDT",
        side="BUY",
        quantity="10.0",
        price="100",
        order_type="LIMIT"
    )
    assert decision1["allowed"] is True
    
    # Wait for cooldown to elapse
    time.sleep(0.6)
    
    # Second entry (after cooldown)
    decision2 = gatekeeper.check_entry(
        symbol="SOLUSDT",
        side="BUY",
        quantity="10.0",
        price="100",
        order_type="LIMIT"
    )
    assert decision2["allowed"] is True

def test_cooldown_per_symbol(gatekeeper):
    """Test that cooldown is tracked per symbol."""
    # Entry for BTC
    gatekeeper.check_entry("BTCUSDT", "BUY", "0.1", "50000", "LIMIT")
    
    # Immediate entry for ETH (different symbol) - should pass
    decision = gatekeeper.check_entry("ETHUSDT", "BUY", "1.0", "3000", "LIMIT")
    assert decision["allowed"] is True

# --- MARKET ORDERS (no price) ---

def test_market_order_without_price(gatekeeper):
    """Test MARKET order with no price (min_notional check skipped)."""
    decision = gatekeeper.check_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.001",
        price=None,  # MARKET orders don't have price
        order_type="MARKET"
    )
    
    # Should pass qty checks, skip notional check
    assert decision["allowed"] is True

# --- MODIFIED PARAMS ---

def test_modified_params_includes_adjusted_values(gatekeeper):
    """Test that modified_params contains adjusted qty/price."""
    decision = gatekeeper.check_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity="0.1234567",  # Will be rounded
        price="50000.123",  # Will be rounded
        order_type="LIMIT"
    )
    
    assert decision["allowed"] is True
    assert "quantity" in decision["modified_params"]
    assert "price" in decision["modified_params"]
    
    # Verify rounding
    adjusted_qty = Decimal(decision["modified_params"]["quantity"])
    adjusted_price = Decimal(decision["modified_params"]["price"])
    assert adjusted_qty == Decimal("0.123456")
    assert adjusted_price == Decimal("50000.12")  # Tick size 0.01

# --- ERROR HANDLING ---

def test_invalid_quantity_type(gatekeeper):
    """Test that invalid qty type is handled gracefully."""
    decision = gatekeeper.check_entry(
        symbol="BTCUSDT",
        side="BUY",
        quantity="not_a_number",
        price="50000",
        order_type="LIMIT"
    )
    
    assert decision["allowed"] is False
    assert decision["reason"] == "GATEKEEPER_ERROR"

# --- RESET COOLDOWN (for testing) ---

def test_reset_cooldown(gatekeeper):
    """Test cooldown reset functionality."""
    # Entry
    gatekeeper.check_entry("BTCUSDT", "BUY", "0.1", "50000", "LIMIT")
    
    # Reset cooldown
    gatekeeper.reset_cooldown("BTCUSDT")
    
    # Immediate second entry should now pass
    decision = gatekeeper.check_entry("BTCUSDT", "BUY", "0.1", "50000", "LIMIT")
    assert decision["allowed"] is True
