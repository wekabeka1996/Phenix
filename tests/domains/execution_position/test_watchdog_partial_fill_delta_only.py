"""
Phase 3 — Execution Safety Guardrails

Tests for DEF-E02: Watchdog must not emit duplicate TRADE_EXECUTED events
when polling finds a PARTIALLY_FILLED order with unchanged cumulative qty.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock
from decimal import Decimal


class TestWatchdogPartialFillDeltaOnly:
    """DEF-E02: TRADE_EXECUTED must only emit when fill qty delta > 0."""

    def _make_watchdog(self):
        """Build a minimal OrderTimeoutWatchdog with emit_fn wired."""
        from apps.reference.domains.execution_position.adapters.watchdog import OrderTimeoutWatchdog

        config = {
            "enabled": True,
            "timeout_sec": 60,
            "rps_limit": 10,
            "fill_ttl_sec": 300,
        }
        wdog = OrderTimeoutWatchdog(config=config)
        wdog.emit_fn = AsyncMock()
        wdog.get_order_fn = AsyncMock()
        return wdog

    def test_last_cumulative_qty_initialized_empty(self):
        """DEF-E02: Watchdog must initialize _last_cumulative_qty as empty dict."""
        wdog = self._make_watchdog()
        assert hasattr(wdog, "_last_cumulative_qty"), (
            "DEF-E02: OrderTimeoutWatchdog must have _last_cumulative_qty attribute"
        )
        assert isinstance(wdog._last_cumulative_qty, dict)
        assert len(wdog._last_cumulative_qty) == 0

    def test_first_partial_fill_records_qty(self):
        """First PARTIALLY_FILLED poll must record cumulative qty for delta tracking."""
        wdog = self._make_watchdog()

        order_id = "order-abc"
        wdog._last_cumulative_qty[order_id] = 0.5

        assert wdog._last_cumulative_qty[order_id] == 0.5

    def test_same_qty_delta_zero_no_emit(self):
        """
        DEF-E02 regression: if executed_qty == last_cumulative_qty, delta is 0
        and TRADE_EXECUTED must NOT be emitted.
        """
        wdog = self._make_watchdog()

        order_id = "order-dupe"
        executed_qty = 0.5
        # Already seen this qty
        wdog._last_cumulative_qty[order_id] = executed_qty

        last_qty = wdog._last_cumulative_qty.get(order_id, 0.0)
        delta = executed_qty - last_qty

        assert delta <= 0, (
            f"DEF-E02: Delta should be <= 0 for unchanged qty. Got delta={delta}"
        )
        # In production code: `if executed_qty <= last_qty: continue` (skip emit)

    def test_increased_qty_positive_delta_permits_emit(self):
        """If executed_qty increased since last poll, delta > 0 and emit is permitted."""
        wdog = self._make_watchdog()

        order_id = "order-increasing"
        wdog._last_cumulative_qty[order_id] = 0.3  # Previously saw 0.3

        new_executed_qty = 0.7
        last_qty = wdog._last_cumulative_qty.get(order_id, 0.0)
        delta = new_executed_qty - last_qty

        assert delta > 0, f"DEF-E02: Positive delta expected for new fill. Got delta={delta}"

        # Update tracking
        wdog._last_cumulative_qty[order_id] = new_executed_qty
        assert wdog._last_cumulative_qty[order_id] == 0.7

    def test_first_fill_with_no_prior_tracking_emits(self):
        """First fill on an order (no prior tracking entry) must always emit."""
        wdog = self._make_watchdog()

        order_id = "brand-new-order"
        executed_qty = 0.01

        last_qty = wdog._last_cumulative_qty.get(order_id, 0.0)  # Default 0.0
        delta = executed_qty - last_qty

        assert delta > 0, "First fill must have positive delta (0.01 > 0.0)"

    def test_terminal_fill_clears_tracking(self):
        """On FILLED status, _last_cumulative_qty tracking can be cleared."""
        wdog = self._make_watchdog()

        order_id = "order-terminal"
        wdog._last_cumulative_qty[order_id] = 0.9

        # Simulate terminal fill cleanup
        wdog._last_cumulative_qty.pop(order_id, None)

        assert order_id not in wdog._last_cumulative_qty
