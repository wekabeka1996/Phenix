from apps.reference.domains.execution_position.exposure_guard import (
    ExposureGuard,
)
from decimal import Decimal
import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class TestExposureGuard:
    """Test ExposureGuard functionality."""

    def test_initialization(self):
        """Test ExposureGuard initialization with config."""
        config = {
            "trading": {
                "execution": {
                    "exposure": {
                        "max_portfolio_fraction": 0.25,
                        "count_pending_orders": False,
                        "exclude_reduce_only": True,
                    }
                }
            }
        }
        guard = ExposureGuard(config)
        # ExposureGuard correctly extracts values from dict config
        assert guard.max_portfolio_fraction == Decimal("0.25")  # from config
        assert guard.count_pending_orders is False
        assert guard.exclude_reduce_only is True

    def test_default_config(self):
        """Test ExposureGuard with default config."""
        config = {}
        guard = ExposureGuard(config)
        assert guard.max_portfolio_fraction == Decimal("0.20")  # default
        assert guard.count_pending_orders is True  # default
        assert guard.exclude_reduce_only is True  # default

    def test_portfolio_update(self):
        """Test portfolio state updates."""
        import time
        config = {}
        guard = ExposureGuard(config)

        # Update with equity and positions
        now_ms = int(time.time() * 1000)
        payload = {
            "equity_free_usdt": "10000.0",
            "open_positions_margin_usd": "5000.0",  # Updated key name
            "positions_last_ts_ms": now_ms,  # Current timestamp
        }

        guard.on_portfolio(payload)  # Updated method name

        # Verify portfolio state was stored
        assert guard._latest_portfolio_state == payload

    def test_can_open_within_limit(self):
        """Test can_open when within exposure limit."""
        import time
        config = {}
        guard = ExposureGuard(config)

        # Setup portfolio state
        now_ms = int(time.time() * 1000)
        portfolio_state = {
            "equity_free_usdt": "10000.0",
            "open_positions_margin_usd": "1000.0",  # Current margin used
            "positions_last_ts_ms": now_ms,  # Recent timestamp (now)
        }

        # New position: 500 notional
        result = guard.can_open("BTCUSDT", Decimal("500.0"), portfolio_state)

        assert result["allowed"] is True

    def test_can_open_exceeds_limit(self):
        """Test can_open when exceeding exposure limit - returns shrunk notional."""
        import time
        config = {}
        guard = ExposureGuard(config)

        # Setup portfolio state with high margin usage
        # equity = 10000, margin_limit = 2000 (0.20 * 10000)
        # current margin = 1800, available = 200
        # new notional = 5000, margin_needed = 5000/20 = 250
        # Component will shrink to available = 200 * leverage = 200 * 20 = 4000
        now_ms = int(time.time() * 1000)
        portfolio_state = {
            "equity_free_usdt": "10000.0",
            "open_positions_margin_usd": "1800.0",  # Close to limit
            "positions_last_ts_ms": now_ms,
        }

        # New position with notional 5000 would exceed limit
        result = guard.can_open("BTCUSDT", Decimal("5000.0"), portfolio_state)

        # Should be shrunk, not rejected
        assert result["allowed"] is True
        assert result["reason"] == "SHRUNK_TO_FIT"
        assert result["shrink_notional"] == Decimal("4000.000")

    def test_pending_orders_counting(self):
        """Test counting pending orders in exposure."""
        config = {"trading": {"execution": {
            "exposure": {"count_pending_orders": True}}}}
        guard = ExposureGuard(config)

        # Reserve pending order
        guard.reserve("key1", Decimal("500.0"))

        # Check that reservation exists
        assert "key1" in guard.state.reservations
        assert guard.state.reservations["key1"] == Decimal("500.0")

    def test_pending_orders_not_counting(self):
        """Test not counting pending orders when disabled."""
        config = {"trading": {"execution": {
            "exposure": {"count_pending_orders": False}}}}
        guard = ExposureGuard(config)

        # Reserve pending order
        guard.reserve("key1", Decimal("500.0"))

        # Reservation should still exist (just not counted in exposure)
        assert "key1" in guard.state.reservations

    def test_reduce_only_exclusion(self):
        """Test excluding reduce-only orders from pending count."""
        config = {
            "trading": {"execution": {"exposure": {
                "count_pending_orders": True,
                "exclude_reduce_only": True
            }}}
        }
        guard = ExposureGuard(config)

        # Reserve reduce-only order
        guard.reserve("key1", Decimal("500.0"), reduce_only=True)

        # Check that reduce_only flag is stored
        assert "key1" in guard.state.pending_exposure
        assert guard.state.pending_exposure["key1"]["reduce_only"] is True

    def test_reserve_release(self):
        """Test reserve and release operations."""
        config = {}
        guard = ExposureGuard(config)

        # Reserve
        guard.reserve("key1", Decimal("100.0"))
        assert "key1" in guard.state.reservations
        assert guard.state.reservations["key1"] == Decimal("100.0")

        # Release
        guard.release("key1")
        assert "key1" not in guard.state.reservations

        # Release non-existent (should not error)
        guard.release("nonexistent")

    def test_exposure_summary(self):
        """Test exposure summary calculation."""
        config = {}
        guard = ExposureGuard(config)

        guard.reserve("key1", Decimal("500.0"))

        # Get summary - no parameters needed
        summary = guard.get_exposure_summary()

        assert "reservations_count" in summary
        assert summary["reservations_count"] == 1
        assert summary["reservations_usd"] == 500.0
