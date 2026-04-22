"""
TASK49: Tests for Atomic CAS Entry Reservation.

Verifies that try_reserve_entry() properly prevents TOCTOU race conditions
by atomically checking for existing in-flight entries and reserving a slot.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from apps.reference.domains.execution_position.order_index import OrderIndex, OrderRef


class TestTryReserveEntry:
    """Test cases for try_reserve_entry() CAS operation."""

    @pytest.fixture
    def order_index(self):
        return OrderIndex(ttl_sec=3600)

    def test_first_reserve_succeeds(self, order_index):
        """First reservation for a symbol should succeed."""
        result = order_index.try_reserve_entry("BTCUSDT", "rid-001")
        assert result is True

    def test_second_reserve_same_symbol_fails(self, order_index):
        """Second reservation for same symbol should fail while first is active."""
        result1 = order_index.try_reserve_entry("BTCUSDT", "rid-001")
        result2 = order_index.try_reserve_entry("BTCUSDT", "rid-002")
        
        assert result1 is True
        assert result2 is False

    def test_reserve_different_symbols_both_succeed(self, order_index):
        """Reservations for different symbols should both succeed."""
        result1 = order_index.try_reserve_entry("BTCUSDT", "rid-001")
        result2 = order_index.try_reserve_entry("ETHUSDT", "rid-002")
        
        assert result1 is True
        assert result2 is True

    def test_reserve_after_terminal_succeeds(self, order_index):
        """Reservation should succeed after previous entry marked terminal."""
        result1 = order_index.try_reserve_entry("BTCUSDT", "rid-001")
        assert result1 is True
        
        # Mark as terminal
        ref = order_index.get(rid="rid-001")
        order_index.mark_terminal(ref)
        
        # New reservation should succeed
        result2 = order_index.try_reserve_entry("BTCUSDT", "rid-002")
        assert result2 is True

    def test_reserve_after_cancel_succeeds(self, order_index):
        """Reservation should succeed after previous reservation cancelled."""
        result1 = order_index.try_reserve_entry("BTCUSDT", "rid-001")
        assert result1 is True
        
        # Cancel reservation
        cancelled = order_index.cancel_reservation("rid-001")
        assert cancelled is True
        
        # New reservation should succeed
        result2 = order_index.try_reserve_entry("BTCUSDT", "rid-002")
        assert result2 is True

    def test_cancel_nonexistent_returns_false(self, order_index):
        """Cancelling a non-existent reservation returns False."""
        result = order_index.cancel_reservation("nonexistent-rid")
        assert result is False

    def test_cancel_committed_order_returns_false(self, order_index):
        """Cancelling an already committed order (with clientOrderId) returns False."""
        order_index.try_reserve_entry("BTCUSDT", "rid-001")
        
        # Simulate order placement - upsert with clientOrderId
        order_index.upsert_from_open(
            rid="rid-001",
            idempotent_key="rid-001",
            clientOrderId="ENTRY-abc123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="ENTRY",
        )
        
        # Cancel should fail - order is already committed
        result = order_index.cancel_reservation("rid-001")
        assert result is False

    def test_reserve_empty_symbol_fails(self, order_index):
        """Reservation with empty symbol should fail."""
        result = order_index.try_reserve_entry("", "rid-001")
        assert result is False

    def test_reserve_empty_rid_fails(self, order_index):
        """Reservation with empty rid should fail."""
        result = order_index.try_reserve_entry("BTCUSDT", "")
        assert result is False

    def test_has_in_flight_after_reserve(self, order_index):
        """has_in_flight_entry should return True after reserve."""
        order_index.try_reserve_entry("BTCUSDT", "rid-001")
        assert order_index.has_in_flight_entry("BTCUSDT") is True

    def test_has_in_flight_after_cancel(self, order_index):
        """has_in_flight_entry should return False after cancel."""
        order_index.try_reserve_entry("BTCUSDT", "rid-001")
        order_index.cancel_reservation("rid-001")
        assert order_index.has_in_flight_entry("BTCUSDT") is False

    def test_get_in_flight_entry_ignores_same_rid(self, order_index):
        """Same-rid lookups should not block their own reservation."""
        order_index.try_reserve_entry("BTCUSDT", "rid-001")

        assert order_index.get_in_flight_entry("BTCUSDT") is not None
        assert order_index.get_in_flight_entry(
            "BTCUSDT",
            exclude_rid="rid-001",
        ) is None

    def test_get_in_flight_entry_ignores_aged_out_reservations(self):
        """Aged-out entry refs should not block the one-open-order guard forever."""
        order_index = OrderIndex(ttl_sec=3600, entry_guard_ttl_sec=1)
        order_index.try_reserve_entry("BTCUSDT", "rid-001")

        ref = order_index.get(rid="rid-001")
        assert ref is not None
        ref.created_ts = time.time() - 5

        assert order_index.get_in_flight_entry("BTCUSDT") is None
        assert order_index.has_in_flight_entry("BTCUSDT") is False


class TestTryReserveEntryConcurrency:
    """Concurrency tests for try_reserve_entry() to verify race condition fix."""

    def test_concurrent_reserves_only_one_wins(self):
        """Only one concurrent reservation for same symbol should succeed."""
        order_index = OrderIndex(ttl_sec=3600)
        results = []
        barrier = threading.Barrier(10)

        def try_reserve(rid: str):
            barrier.wait()  # Sync all threads to start simultaneously
            result = order_index.try_reserve_entry("BTCUSDT", rid)
            results.append(result)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(try_reserve, f"rid-{i:03d}")
                for i in range(10)
            ]
            for f in futures:
                f.result()

        # Exactly ONE should succeed, 9 should fail
        assert results.count(True) == 1
        assert results.count(False) == 9

    def test_concurrent_reserves_different_symbols_all_succeed(self):
        """Concurrent reservations for different symbols should all succeed."""
        order_index = OrderIndex(ttl_sec=3600)
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
        results = []
        barrier = threading.Barrier(5)

        def try_reserve(symbol: str, rid: str):
            barrier.wait()
            result = order_index.try_reserve_entry(symbol, rid)
            results.append((symbol, result))

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(try_reserve, sym, f"rid-{sym}")
                for sym in symbols
            ]
            for f in futures:
                f.result()

        # All should succeed (different symbols)
        assert all(r[1] for r in results)

    def test_stress_reserve_cancel_cycle(self):
        """Stress test rapid reserve/cancel cycles."""
        order_index = OrderIndex(ttl_sec=3600)
        success_count = 0
        iterations = 100

        for i in range(iterations):
            rid = f"rid-{i:04d}"
            if order_index.try_reserve_entry("BTCUSDT", rid):
                success_count += 1
                order_index.cancel_reservation(rid)

        # All should succeed since we cancel after each
        assert success_count == iterations

    def test_concurrent_reserve_and_cancel(self):
        """Test concurrent reserve and cancel operations don't corrupt state."""
        order_index = OrderIndex(ttl_sec=3600)
        errors = []

        def reserve_worker():
            for i in range(50):
                rid = f"reserve-{i:03d}"
                order_index.try_reserve_entry("BTCUSDT", rid)
                time.sleep(0.001)

        def cancel_worker():
            for i in range(50):
                rid = f"reserve-{i:03d}"
                order_index.cancel_reservation(rid)
                time.sleep(0.001)

        def check_worker():
            for _ in range(100):
                try:
                    # Should never raise - just checking for corruption
                    order_index.has_in_flight_entry("BTCUSDT")
                except Exception as e:
                    errors.append(str(e))
                time.sleep(0.001)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(reserve_worker),
                executor.submit(cancel_worker),
                executor.submit(check_worker),
            ]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Errors during concurrent access: {errors}"


class TestTryReserveEntryIntegrationWithUpsert:
    """Test try_reserve_entry integration with upsert_from_open."""

    @pytest.fixture
    def order_index(self):
        return OrderIndex(ttl_sec=3600)

    def test_reserve_then_upsert_preserves_intent(self, order_index):
        """Reservation followed by upsert should preserve the entry."""
        # Reserve first
        reserved = order_index.try_reserve_entry("BTCUSDT", "rid-001")
        assert reserved is True

        # Upsert (simulating _dispatch_open in main.py)
        order_index.upsert_from_open(
            rid="rid-001",
            idempotent_key="rid-001",
            clientOrderId="ENTRY-abc123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="ENTRY_INTENT",
        )

        # Still in-flight
        assert order_index.has_in_flight_entry("BTCUSDT") is True

        # Second reserve should fail
        reserved2 = order_index.try_reserve_entry("BTCUSDT", "rid-002")
        assert reserved2 is False

    def test_reserve_upsert_terminal_allows_new_reserve(self, order_index):
        """After marking terminal, new reservation should be allowed."""
        # Reserve + upsert
        order_index.try_reserve_entry("BTCUSDT", "rid-001")
        order_index.upsert_from_open(
            rid="rid-001",
            idempotent_key="rid-001",
            clientOrderId="ENTRY-abc123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="ENTRY",
        )

        # Mark terminal (order filled/cancelled)
        ref = order_index.get(rid="rid-001")
        order_index.mark_terminal(ref)

        # New reservation should succeed
        reserved = order_index.try_reserve_entry("BTCUSDT", "rid-002")
        assert reserved is True
