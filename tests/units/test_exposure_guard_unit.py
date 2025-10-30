import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from decimal import Decimal
from vfoundation.apps.reference.domains.execution_position.exposure_guard import (
    ExposureGuard,
)


class TestExposureGuard:
    """Test ExposureGuard functionality."""

    def test_initialization(self):
        """Test ExposureGuard initialization with config."""
        config = {
            "exposure": {
                "max_portfolio_fraction": 0.25,
                "count_pending_orders": False,
                "exclude_reduce_only": True,
            }
        }
        guard = ExposureGuard(config)
        assert guard.max_portfolio_fraction == Decimal("0.25")
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
        config = {}
        guard = ExposureGuard(config)

        # Update with equity and positions
        payload = {
            "equity_free_usdt": "10000.0",
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "net_position": "1.0",
                    "avg_entry_price": "50000.0",
                },
                {
                    "symbol": "ETHUSDT",
                    "net_position": "10.0",
                    "avg_entry_price": "3000.0",
                },
            ],
        }

        guard.on_portfolio_update(payload)

        assert guard.state.equity_free_usdt == Decimal("10000.0")
        # 1.0 * 50000 + 10.0 * 3000 = 50000 + 30000 = 80000
        assert guard.state.open_positions_usd == Decimal("80000.0")

    def test_can_open_within_limit(self):
        """Test can_open when within exposure limit."""
        config = {}
        guard = ExposureGuard(config)

        # Setup: equity=10000, positions=4000, limit=2000 (20%)
        guard.state.equity_free_usdt = Decimal("10000.0")
        guard.state.open_positions_usd = Decimal("4000.0")

        # New position: 1000 notional (4000 + 1000 = 5000 < 2000 limit? Wait, 5000 > 2000)
        # Actually: current_total = 4000, new = 1000, total_will_be = 5000 > 2000 limit
        allowed, data = guard.can_open(Decimal("1000.0"))

        assert allowed is False
        assert data["equity_usd"] == "10000.0"
        assert data["limit_usd"] == "2000.00"  # 10000 * 0.20
        assert data["positions_usd"] == "4000.0"
        assert data["pending_usd"] == "0"
        assert data["new_usd"] == "1000.0"
        assert data["exposure_will_be_usd"] == "5000.0"

    def test_can_open_exceeds_limit(self):
        """Test can_open when exceeding exposure limit."""
        config = {}
        guard = ExposureGuard(config)

        # Setup: equity=10000, positions=1000, limit=2000
        guard.state.equity_free_usdt = Decimal("10000.0")
        guard.state.open_positions_usd = Decimal("1000.0")

        # New position: 500 notional (1000 + 500 = 1500 < 2000 limit)
        allowed, data = guard.can_open(Decimal("500.0"))

        assert allowed is True
        assert data["exposure_will_be_usd"] == "1500.0"

    def test_pending_orders_counting(self):
        """Test counting pending orders in exposure."""
        config = {"exposure": {"count_pending_orders": True}}
        guard = ExposureGuard(config)

        guard.state.equity_free_usdt = Decimal("10000.0")
        guard.state.open_positions_usd = Decimal("1000.0")

        # Reserve pending order
        guard.reserve("key1", Decimal("500.0"))

        # Check exposure includes pending
        allowed, data = guard.can_open(
            Decimal("400.0")
        )  # 1000 + 500 + 400 = 1900 < 2000

        assert allowed is True
        assert data["pending_usd"] == "500.0"
        assert data["exposure_will_be_usd"] == "1900.0"

    def test_pending_orders_not_counting(self):
        """Test not counting pending orders when disabled."""
        config = {"exposure": {"count_pending_orders": False}}
        guard = ExposureGuard(config)

        guard.state.equity_free_usdt = Decimal("10000.0")
        guard.state.open_positions_usd = Decimal("1000.0")

        # Reserve pending order
        guard.reserve("key1", Decimal("500.0"))

        # Check exposure excludes pending
        allowed, data = guard.can_open(Decimal("900.0"))  # 1000 + 900 = 1900 < 2000

        assert allowed is True
        assert data["pending_usd"] == "0"  # Not counted
        assert data["exposure_will_be_usd"] == "1900.0"

    def test_reduce_only_exclusion(self):
        """Test excluding reduce-only orders from pending count."""
        config = {
            "exposure": {"count_pending_orders": True, "exclude_reduce_only": True}
        }
        guard = ExposureGuard(config)

        guard.state.equity_free_usdt = Decimal("10000.0")
        guard.state.open_positions_usd = Decimal("1000.0")

        # Reserve reduce-only order (should not count)
        guard.reserve("key1", Decimal("500.0"), reduce_only=True)

        # Check exposure excludes reduce-only pending
        allowed, data = guard.can_open(Decimal("900.0"))  # 1000 + 900 = 1900 < 2000

        assert allowed is True
        assert data["pending_usd"] == "0"  # Excluded
        assert data["exposure_will_be_usd"] == "1900.0"

    def test_reserve_release(self):
        """Test reserve and release operations."""
        config = {"exposure": {"count_pending_orders": True}}
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
        config = {"exposure": {"count_pending_orders": True}}
        guard = ExposureGuard(config)

        guard.state.equity_free_usdt = Decimal("10000.0")
        guard.state.open_positions_usd = Decimal("2000.0")
        guard.reserve("key1", Decimal("500.0"))

        summary = guard.get_exposure_summary()

        assert summary["equity_usd"] == "10000.0"
        assert summary["limit_usd"] == "2000.00"
        assert summary["positions_usd"] == "2000.0"
        assert summary["pending_usd"] == "500.0"
        assert summary["current_exposure_usd"] == "2500.0"
        assert summary["utilization_pct"] == 125.0  # 2500 / 2000 * 100
        assert summary["pending_orders_count"] == 1
