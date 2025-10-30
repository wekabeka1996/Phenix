"""
Unit tests for ExposureGuard TTL functionality.

Tests expire_stale method and TTL-based reservation expiration.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from decimal import Decimal
from vfoundation.apps.reference.domains.execution_position.exposure_guard import (
    ExposureGuard,
)
import time


def test_expire_stale_releases_pending(monkeypatch):
    """Test that expire_stale releases expired reservations."""
    guard = ExposureGuard({"exposure": {"pending_reservation_ttl_sec": 1}})
    guard.on_portfolio_update({"equity_free_usdt": "1000", "positions": []})

    # Reserve some exposure
    guard.reserve("k1", Decimal("100"))
    guard.reserve("k2", Decimal("200"))

    # Verify reservations exist
    assert len(guard.state.reservations) == 2
    assert str(guard.state.pending_open_usd) == "300"

    # Fast-forward time beyond TTL
    future_time = time.time() + 2
    monkeypatch.setattr(time, "time", lambda: future_time)

    # Cleanup expired reservations
    expired = guard.expire_stale()
    assert "k1" in expired
    assert "k2" in expired
    assert len(expired) == 2

    # Verify reservations are released
    assert len(guard.state.reservations) == 0
    assert str(guard.state.pending_open_usd) == "0"


def test_expire_stale_partial_expiration(monkeypatch):
    """Test cleanup when only some reservations are expired."""
    guard = ExposureGuard({"exposure": {"pending_reservation_ttl_sec": 10}})
    guard.on_portfolio_update({"equity_free_usdt": "1000", "positions": []})

    # Reserve with different timestamps
    guard.reserve("k1", Decimal("100"))
    time.sleep(0.1)  # Small delay
    guard.reserve("k2", Decimal("200"))

    # Manually set k1 to be expired (15 seconds ago)
    guard.state.reservations_ts["k1"] = time.time() - 15

    # Fast-forward time to ensure k1 is expired
    future_time = time.time() + 5  # 5 seconds in future
    monkeypatch.setattr(time, "time", lambda: future_time)

    # Cleanup
    expired = guard.expire_stale()
    assert "k1" in expired
    assert "k2" not in expired
    assert len(expired) == 1

    # Verify only k1 is released
    assert len(guard.state.reservations) == 1
    assert "k2" in guard.state.reservations
    assert str(guard.state.pending_open_usd) == "200"


def test_expire_stale_disabled_ttl():
    """Test cleanup when TTL is disabled (0)."""
    guard = ExposureGuard({"exposure": {"pending_reservation_ttl_sec": 0}})
    guard.on_portfolio_update({"equity_free_usdt": "1000", "positions": []})

    guard.reserve("k1", Decimal("100"))
    guard.state.reservations_ts["k1"] = time.time() - 1000  # Very old

    # Cleanup should do nothing
    expired = guard.expire_stale()
    assert len(expired) == 0
    assert len(guard.state.reservations) == 1
    assert str(guard.state.pending_open_usd) == "100"


def test_expire_stale_empty_reservations():
    """Test cleanup when no reservations exist."""
    guard = ExposureGuard({"exposure": {"pending_reservation_ttl_sec": 1}})
    guard.on_portfolio_update({"equity_free_usdt": "1000", "positions": []})

    expired = guard.expire_stale()
    assert len(expired) == 0


def test_reserve_stores_timestamp():
    """Test that reserve stores timestamp correctly."""
    guard = ExposureGuard({"exposure": {"pending_reservation_ttl_sec": 300}})
    guard.on_portfolio_update({"equity_free_usdt": "1000", "positions": []})

    before = time.time()
    guard.reserve("k1", Decimal("100"))
    after = time.time()

    ts = guard.state.reservations_ts["k1"]
    assert before <= ts <= after
    assert guard.state.reservations["k1"] == Decimal("100")
    assert guard.state.reservations["k1"] is not False
