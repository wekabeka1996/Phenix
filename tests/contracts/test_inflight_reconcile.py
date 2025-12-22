"""
Tests for In-Flight Order Reconciler.

TASK51-C: TDD tests for in-flight TTL and reconciliation.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, Optional, List

from apps.reference.domains.inflight_reconcile.config import InFlightConfig
from apps.reference.domains.inflight_reconcile.reconciler import (
    InFlightReconciler,
    InFlightEntry,
    InFlightStatus,
    ReconcileResult,
    TERMINAL_STATUSES,
)


# ==============================================================================
# Test Fixtures
# ==============================================================================


def make_mock_checker(
    order_status: Optional[Dict[str, Any]] = None,
    open_orders: Optional[List[Dict[str, Any]]] = None,
):
    """Create mock exchange checker."""
    checker = AsyncMock()
    checker.get_order_status = AsyncMock(return_value=order_status)
    checker.get_open_orders = AsyncMock(return_value=open_orders or [])
    return checker


# ==============================================================================
# Config Tests
# ==============================================================================


class TestInFlightConfig:
    """Test InFlightConfig parsing and defaults."""
    
    def test_default_values(self):
        """Default config should have sensible values."""
        config = InFlightConfig()
        
        assert config.inflight_ttl_sec == 60
        assert config.max_ttl_sec == 120
        assert config.reconcile_interval_sec == 10
    
    def test_from_yaml_dict(self):
        """Should parse YAML dict correctly."""
        data = {
            "inflight_ttl_sec": 30,
            "max_ttl_sec": 90,
            "reconcile_interval_sec": 5,
        }
        
        config = InFlightConfig.from_yaml_dict(data)
        
        assert config.inflight_ttl_sec == 30
        assert config.max_ttl_sec == 90
        assert config.reconcile_interval_sec == 5
    
    def test_from_ssot(self):
        """Should parse from domains.yaml structure."""
        domains_config = {
            "execution_position": {
                "inflight_reconcile": {
                    "inflight_ttl_sec": 45,
                    "max_ttl_sec": 100,
                }
            }
        }
        
        config = InFlightConfig.from_ssot(domains_config)
        
        assert config.inflight_ttl_sec == 45
        assert config.max_ttl_sec == 100


# ==============================================================================
# InFlightEntry Tests
# ==============================================================================


class TestInFlightEntry:
    """Test InFlightEntry dataclass."""
    
    def test_age_calculation(self):
        """age_sec should calculate correctly."""
        entry = InFlightEntry(
            rid="test-123",
            symbol="ETHUSDT",
        )
        
        # Give it a moment to age
        time.sleep(0.01)
        
        assert entry.age_sec > 0
        assert entry.age_sec < 1
    
    def test_is_terminal_pending(self):
        """PENDING should not be terminal."""
        entry = InFlightEntry(
            rid="test-123",
            symbol="ETHUSDT",
            status=InFlightStatus.PENDING,
        )
        
        assert entry.is_terminal is False
    
    def test_is_terminal_filled(self):
        """FILLED should be terminal."""
        entry = InFlightEntry(
            rid="test-123",
            symbol="ETHUSDT",
            status=InFlightStatus.FILLED,
        )
        
        assert entry.is_terminal is True
    
    def test_is_terminal_not_found(self):
        """NOT_FOUND should be terminal."""
        entry = InFlightEntry(
            rid="test-123",
            symbol="ETHUSDT",
            status=InFlightStatus.NOT_FOUND,
        )
        
        assert entry.is_terminal is True


# ==============================================================================
# Reconciler Core Tests
# ==============================================================================


class TestInFlightReconciler:
    """Test InFlightReconciler core functionality."""
    
    def test_register_entry(self):
        """Should register in-flight entry."""
        reconciler = InFlightReconciler()
        
        entry = reconciler.register(
            rid="test-123",
            symbol="ETHUSDT",
            client_order_id="ENTRY-abc123",
        )
        
        assert entry.rid == "test-123"
        assert entry.symbol == "ETHUSDT"
        assert entry.client_order_id == "ENTRY-abc123"
        assert reconciler.has_in_flight("ETHUSDT") is True
    
    def test_has_in_flight(self):
        """Should detect in-flight orders."""
        reconciler = InFlightReconciler()
        
        assert reconciler.has_in_flight("ETHUSDT") is False
        
        reconciler.register(rid="test-123", symbol="ETHUSDT")
        
        assert reconciler.has_in_flight("ETHUSDT") is True
        assert reconciler.has_in_flight("BTCUSDT") is False
    
    def test_update_order_id(self):
        """Should update order IDs after registration."""
        reconciler = InFlightReconciler()
        
        reconciler.register(rid="test-123", symbol="ETHUSDT")
        
        updated = reconciler.update_order_id(
            rid="test-123",
            client_order_id="ENTRY-final",
            exchange_order_id="12345",
        )
        
        assert updated is True
        
        entries = reconciler.get_in_flight("ETHUSDT")
        assert len(entries) == 1
        assert entries[0].client_order_id == "ENTRY-final"
        assert entries[0].exchange_order_id == "12345"
    
    def test_mark_terminal(self):
        """Should mark entry as terminal."""
        reconciler = InFlightReconciler()
        
        reconciler.register(rid="test-123", symbol="ETHUSDT")
        
        marked = reconciler.mark_terminal(
            rid="test-123",
            status=InFlightStatus.FILLED,
            reason="Order filled",
        )
        
        assert marked is True
        
        # Terminal entries should not count as in-flight
        assert reconciler.has_in_flight("ETHUSDT") is False
    
    def test_clear_entry(self):
        """Should clear in-flight entry."""
        reconciler = InFlightReconciler()
        
        reconciler.register(rid="test-123", symbol="ETHUSDT")
        
        cleared = reconciler.clear("test-123")
        
        assert cleared is True
        assert reconciler.has_in_flight("ETHUSDT") is False
    
    def test_stats(self):
        """Should return correct statistics."""
        reconciler = InFlightReconciler()
        
        reconciler.register(rid="r1", symbol="ETHUSDT")
        reconciler.register(rid="r2", symbol="ETHUSDT")
        reconciler.register(rid="r3", symbol="BTCUSDT")
        reconciler.mark_terminal("r1", InFlightStatus.FILLED, "filled")
        
        stats = reconciler.stats()
        
        assert stats["total"] == 3
        assert stats["pending"] == 2
        assert stats["terminal"] == 1


# ==============================================================================
# TASK51-C Required Tests
# ==============================================================================


class TestInFlightExpiresAndReconciles:
    """TASK51-C: Test in-flight expiry and reconciliation."""
    
    @pytest.mark.asyncio
    async def test_inflight_expires_and_reconciles(self):
        """
        TASK51-C Test 1: In-flight should expire and reconcile via REST.
        
        When TTL expires, reconciler should:
        1. Check order status via REST
        2. If terminal/not-found -> clear in-flight
        3. Allow new OPEN
        """
        config = InFlightConfig(inflight_ttl_sec=0)  # Immediate expiry for test
        checker = make_mock_checker(order_status={"status": "FILLED"})
        
        reconciler = InFlightReconciler(config=config, exchange_checker=checker)
        
        # Register in-flight order
        reconciler.register(
            rid="test-123",
            symbol="ETHUSDT",
            client_order_id="ENTRY-abc",
        )
        
        assert reconciler.has_in_flight("ETHUSDT") is True
        
        # Get expired entries (should be immediate since TTL=0)
        expired = reconciler.get_expired_entries()
        assert len(expired) == 1
        
        # Reconcile
        result = await reconciler.reconcile_entry(expired[0])
        
        assert result.new_status == InFlightStatus.FILLED
        assert result.cleared is True
        
        # In-flight should be cleared
        assert reconciler.has_in_flight("ETHUSDT") is False
    
    @pytest.mark.asyncio
    async def test_inflight_cleared_on_terminal_status(self):
        """
        TASK51-C Test 2: In-flight cleared when exchange reports terminal status.
        
        Terminal statuses: FILLED, CANCELED, EXPIRED, REJECTED, NOT_FOUND
        """
        for exchange_status, expected_status in [
            ("FILLED", InFlightStatus.FILLED),
            ("CANCELED", InFlightStatus.CANCELED),
            ("CANCELLED", InFlightStatus.CANCELED),
            ("EXPIRED", InFlightStatus.EXPIRED),
            ("REJECTED", InFlightStatus.REJECTED),
        ]:
            config = InFlightConfig(inflight_ttl_sec=0)
            checker = make_mock_checker(order_status={"status": exchange_status})
            
            reconciler = InFlightReconciler(config=config, exchange_checker=checker)
            reconciler.register(rid="test", symbol="ETHUSDT")
            
            expired = reconciler.get_expired_entries()
            result = await reconciler.reconcile_entry(expired[0])
            
            assert result.new_status == expected_status, f"Failed for {exchange_status}"
            assert result.cleared is True, f"Should be cleared for {exchange_status}"
            assert reconciler.has_in_flight("ETHUSDT") is False
    
    @pytest.mark.asyncio
    async def test_inflight_cleared_on_not_found(self):
        """
        TASK51-C Test 2b: In-flight cleared when order not found on exchange.
        """
        config = InFlightConfig(inflight_ttl_sec=0)
        checker = make_mock_checker(order_status=None)  # Not found
        
        reconciler = InFlightReconciler(config=config, exchange_checker=checker)
        reconciler.register(rid="test-123", symbol="ETHUSDT")
        
        expired = reconciler.get_expired_entries()
        result = await reconciler.reconcile_entry(expired[0])
        
        assert result.new_status == InFlightStatus.NOT_FOUND
        assert result.cleared is True
        assert reconciler.has_in_flight("ETHUSDT") is False
    
    def test_inflight_blocks_before_ttl(self):
        """
        TASK51-C Test 3: In-flight should block new orders before TTL.
        
        The has_in_flight check should return True before TTL expires.
        """
        config = InFlightConfig(inflight_ttl_sec=3600)  # Long TTL
        reconciler = InFlightReconciler(config=config)
        
        # Register in-flight
        reconciler.register(rid="test-123", symbol="ETHUSDT")
        
        # Should block (has_in_flight returns True)
        assert reconciler.has_in_flight("ETHUSDT") is True
        
        # No entries should be expired yet
        expired = reconciler.get_expired_entries()
        assert len(expired) == 0


class TestMaxTTLForceCleanup:
    """Test max TTL force cleanup."""
    
    @pytest.mark.asyncio
    async def test_max_ttl_force_clears(self):
        """Max TTL should force-clear without exchange check."""
        config = InFlightConfig(inflight_ttl_sec=0, max_ttl_sec=0)  # Both immediate
        
        # No exchange checker - should still work
        reconciler = InFlightReconciler(config=config, exchange_checker=None)
        
        entry = reconciler.register(rid="test-123", symbol="ETHUSDT")
        
        # Force age to exceed max TTL
        entry.created_ts = time.time() - 1  # 1 second ago
        
        # Reconcile should force-clear
        result = await reconciler.reconcile_entry(entry)
        
        assert result.new_status == InFlightStatus.TTL_EXPIRED
        assert result.cleared is True
        assert "Max TTL exceeded" in result.reason


class TestReconcileAllExpired:
    """Test bulk reconciliation."""
    
    @pytest.mark.asyncio
    async def test_reconcile_all_expired(self):
        """Should reconcile all expired entries."""
        config = InFlightConfig(inflight_ttl_sec=0)
        checker = make_mock_checker(order_status={"status": "FILLED"})
        
        reconciler = InFlightReconciler(config=config, exchange_checker=checker)
        
        # Register multiple
        reconciler.register(rid="r1", symbol="ETHUSDT")
        reconciler.register(rid="r2", symbol="BTCUSDT")
        reconciler.register(rid="r3", symbol="SOLUSDT")
        
        results = await reconciler.reconcile_all_expired()
        
        assert len(results) == 3
        assert all(r.cleared for r in results)
        
        # All should be cleared
        assert reconciler.has_in_flight("ETHUSDT") is False
        assert reconciler.has_in_flight("BTCUSDT") is False
        assert reconciler.has_in_flight("SOLUSDT") is False


class TestReconcileWithPendingStatus:
    """Test reconciliation when order is still pending."""
    
    @pytest.mark.asyncio
    async def test_pending_not_cleared(self):
        """PENDING status should not clear in-flight."""
        config = InFlightConfig(inflight_ttl_sec=0)
        checker = make_mock_checker(order_status={"status": "NEW"})
        
        reconciler = InFlightReconciler(config=config, exchange_checker=checker)
        reconciler.register(rid="test-123", symbol="ETHUSDT")
        
        expired = reconciler.get_expired_entries()
        result = await reconciler.reconcile_entry(expired[0])
        
        assert result.new_status == InFlightStatus.PENDING
        assert result.cleared is False
        assert reconciler.has_in_flight("ETHUSDT") is True


class TestTerminalStatuses:
    """Test TERMINAL_STATUSES constant."""
    
    def test_terminal_statuses(self):
        """Check terminal statuses set."""
        assert InFlightStatus.FILLED in TERMINAL_STATUSES
        assert InFlightStatus.CANCELED in TERMINAL_STATUSES
        assert InFlightStatus.EXPIRED in TERMINAL_STATUSES
        assert InFlightStatus.NOT_FOUND in TERMINAL_STATUSES
        assert InFlightStatus.REJECTED in TERMINAL_STATUSES
        assert InFlightStatus.TTL_EXPIRED in TERMINAL_STATUSES
        
        # These should NOT be terminal
        assert InFlightStatus.PENDING not in TERMINAL_STATUSES
        assert InFlightStatus.ERROR not in TERMINAL_STATUSES


class TestCleanupTerminal:
    """Test cleanup of terminal entries."""
    
    def test_cleanup_terminal(self):
        """Should clean up all terminal entries."""
        reconciler = InFlightReconciler()
        
        reconciler.register(rid="r1", symbol="ETHUSDT")
        reconciler.register(rid="r2", symbol="BTCUSDT")
        reconciler.mark_terminal("r1", InFlightStatus.FILLED, "filled")
        
        # r1 is terminal, r2 is pending
        cleaned = reconciler.cleanup_terminal()
        
        assert cleaned == 1
        assert reconciler.has_in_flight("BTCUSDT") is True
        
        stats = reconciler.stats()
        assert stats["total"] == 1
        assert stats["pending"] == 1


class TestMultipleSymbols:
    """Test reconciler with multiple symbols."""
    
    def test_independent_symbols(self):
        """In-flight for one symbol shouldn't affect another."""
        reconciler = InFlightReconciler()
        
        reconciler.register(rid="eth-1", symbol="ETHUSDT")
        
        assert reconciler.has_in_flight("ETHUSDT") is True
        assert reconciler.has_in_flight("BTCUSDT") is False
        assert reconciler.has_in_flight("SOLUSDT") is False
    
    def test_multiple_per_symbol(self):
        """Should track multiple in-flight per symbol."""
        reconciler = InFlightReconciler()
        
        reconciler.register(rid="eth-1", symbol="ETHUSDT")
        reconciler.register(rid="eth-2", symbol="ETHUSDT")
        
        entries = reconciler.get_in_flight("ETHUSDT")
        assert len(entries) == 2
        
        # Clear one
        reconciler.clear("eth-1")
        
        entries = reconciler.get_in_flight("ETHUSDT")
        assert len(entries) == 1
        assert entries[0].rid == "eth-2"
