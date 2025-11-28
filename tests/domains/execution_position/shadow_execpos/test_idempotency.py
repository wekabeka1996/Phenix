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


def test_fill_idempotency_cleanup_removes_expired():
    """Test that cleanup removes entries older than max_age_sec."""
    # Short max_age for testing
    idem = FillIdempotency(max_age_sec=0.1)

    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_id": "123",
        "cum_qty": "0.1"
    }

    # Process fill
    assert idem.should_process_fill(payload) is True
    assert len(idem._seen_fills) == 1

    # Wait for expiration
    time.sleep(0.15)

    # Cleanup should remove expired entry
    removed = idem.cleanup()
    assert removed == 1
    assert len(idem._seen_fills) == 0

    # Same fill should now be processed again (key was cleaned up)
    assert idem.should_process_fill(payload) is True


def test_fill_idempotency_cleanup_keeps_fresh():
    """Test that cleanup keeps fresh entries."""
    idem = FillIdempotency(max_age_sec=10.0)

    payload1 = {"symbol": "BTCUSDT", "side": "BUY", "order_id": "1", "cum_qty": "0.1"}
    payload2 = {"symbol": "ETHUSDT", "side": "SELL", "order_id": "2", "cum_qty": "0.5"}

    # Process both fills
    assert idem.should_process_fill(payload1) is True
    assert idem.should_process_fill(payload2) is True
    assert len(idem._seen_fills) == 2

    # Cleanup should remove nothing (all fresh)
    removed = idem.cleanup()
    assert removed == 0
    assert len(idem._seen_fills) == 2


def test_fill_idempotency_cleanup_partial():
    """Test that cleanup removes only expired entries, keeps fresh."""
    idem = FillIdempotency(max_age_sec=1.0)

    # Process first fill
    payload_old = {"symbol": "BTCUSDT", "side": "BUY", "order_id": "old", "cum_qty": "0.1"}
    assert idem.should_process_fill(payload_old) is True

    # Manually age the entry
    key = "BTCUSDT|BUY|old"
    cum, _ = idem._seen_fills[key]
    idem._seen_fills[key] = (cum, time.time() - 5.0)  # 5 seconds old

    # Process fresh fill
    payload_new = {"symbol": "ETHUSDT", "side": "SELL", "order_id": "new", "cum_qty": "0.5"}
    assert idem.should_process_fill(payload_new) is True

    # Cleanup should remove only the old entry
    removed = idem.cleanup()
    assert removed == 1
    assert "BTCUSDT|BUY|old" not in idem._seen_fills
    assert "ETHUSDT|SELL|new" in idem._seen_fills


def test_fill_idempotency_cleanup_empty_store():
    """Test that cleanup handles empty store gracefully."""
    idem = FillIdempotency()

    removed = idem.cleanup()
    assert removed == 0


def test_fill_idempotency_get_stats():
    """Test get_stats returns correct statistics."""
    idem = FillIdempotency(max_age_sec=100.0)

    # Initial stats
    stats = idem.get_stats()
    assert stats["entries"] == 0
    assert stats["cleanup_total"] == 0
    assert stats["max_age_sec"] == 100.0

    # Add some fills
    payload = {"symbol": "BTCUSDT", "side": "BUY", "order_id": "1", "cum_qty": "0.1"}
    idem.should_process_fill(payload)

    stats = idem.get_stats()
    assert stats["entries"] == 1


def test_fill_idempotency_default_max_age():
    """Test that default max_age_sec is 1 hour."""
    idem = FillIdempotency()
    assert idem._max_age_sec == FillIdempotency.DEFAULT_MAX_AGE_SEC
    assert FillIdempotency.DEFAULT_MAX_AGE_SEC == 3600.0


def test_fill_idempotency_cleanup_with_custom_max_age():
    """Test that cleanup can use custom max_age_sec."""
    idem = FillIdempotency(max_age_sec=10.0)  # Default 10 seconds

    payload = {"symbol": "BTCUSDT", "side": "BUY", "order_id": "1", "cum_qty": "0.1"}
    idem.should_process_fill(payload)

    # Manually age entry to 3 seconds
    key = "BTCUSDT|BUY|1"
    cum, _ = idem._seen_fills[key]
    idem._seen_fills[key] = (cum, time.time() - 3.0)

    # Cleanup with default max_age (10s) should keep entry
    removed = idem.cleanup()
    assert removed == 0

    # Cleanup with custom max_age (1s) should remove entry
    removed = idem.cleanup(max_age_sec=1.0)
    assert removed == 1
