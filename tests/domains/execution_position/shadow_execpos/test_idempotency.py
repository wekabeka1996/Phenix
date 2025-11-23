"""
Tests for Shadow ExecPos Idempotency
====================================
"""
import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.shadow_execpos.idempotency import (
    FillIdempotency,
    EventIdempotency,
)

# --- FillIdempotency Tests ---

def test_fill_idempotency_basic():
    idem = FillIdempotency()
    metrics = {}
    
    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_id": "123",
        "cum_qty": "0.1"
    }
    
    # First fill -> Process
    assert idem.should_process_fill(payload, metrics) is True
    assert metrics.get("trade_executed_duplicate_skipped") is None
    
    # Duplicate fill -> Skip
    assert idem.should_process_fill(payload, metrics) is False
    assert metrics["trade_executed_duplicate_skipped"] == 1
    
    # Higher quantity -> Process
    payload_update = payload.copy()
    payload_update["cum_qty"] = "0.2"
    assert idem.should_process_fill(payload_update, metrics) is True
    
    # Lower quantity (out of order) -> Skip
    assert idem.should_process_fill(payload, metrics) is False

def test_fill_idempotency_edge_cases():
    idem = FillIdempotency()
    
    # Missing keys -> Safe default True
    assert idem.should_process_fill({"symbol": "BTC"}) is True
    
    # No cum_qty -> Safe default True
    assert idem.should_process_fill({
        "symbol": "BTC", "side": "BUY", "order_id": "1",
        "cum_qty": None
    }) is True

# --- EventIdempotency Tests ---

def test_event_idempotency_ttl():
    # Short TTL for testing
    idem = EventIdempotency(ttl_seconds=0.1)
    key = "event_1"
    
    assert idem.is_processed(key) is False
    
    idem.mark_processed(key)
    assert idem.is_processed(key) is True
    
    # Wait for expiration
    time.sleep(0.15)
    assert idem.is_processed(key) is False

def test_event_cleanup():
    idem = EventIdempotency(ttl_seconds=0.1)
    
    idem.mark_processed("keep")
    idem.mark_processed("expire")
    
    # Manually age the "expire" key
    idem._store["expire"] = time.time() - 1.0
    
    removed = idem.cleanup()
    assert removed == 1
    assert "expire" not in idem._store
    assert "keep" in idem._store
