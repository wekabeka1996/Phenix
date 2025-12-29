"""
Test OrderIndex.reconcile_snapshot for proper bracket order detection.

This test verifies that STOP_MARKET and TAKE_PROFIT_MARKET orders from
Binance REST API snapshots are correctly stored and retrievable.
"""

import pytest
from apps.reference.domains.execution_position.infra.order_index import (
    OrderIndex,
)
from apps.reference.domains.execution_position.shadow_execpos.converters import (
    normalize_orders,
)


class TestOrderIndexReconcileSnapshot:
    """Test reconcile_snapshot preserves bracket order types."""

    @pytest.fixture
    def order_index(self):
        """Create fresh OrderIndex for each test."""
        return OrderIndex(ttl_sec=3600)

    def test_reconcile_snapshot_preserves_stop_market_type(self, order_index):
        """Verify STOP_MARKET order type is preserved after reconcile_snapshot."""
        symbol = "ETHUSDT"

        # Simulate Binance REST API response for STOP_MARKET (SL) order
        snapshot_orders = [
            {
                "orderId": "12345",
                "clientOrderId": "AUR-ETHUSDT-L-SL-C0-abc123",
                "symbol": symbol,
                "side": "SELL",
                "type": "STOP_MARKET",
                "origType": "STOP_MARKET",
                "origQty": "0.088",
                "executedQty": "0",
                "price": "0",
                "stopPrice": "2955.19",
                "status": "NEW",
                "reduceOnly": False,
                "closePosition": True,
                "time": 1733161440000,
            }
        ]

        # Reconcile
        order_index.reconcile_snapshot(symbol, snapshot_orders)

        # Get orders back
        refs = order_index.get_by_symbol(symbol)
        assert len(refs) == 1

        ref = refs[0]
        assert ref.order_type == "STOP_MARKET", f"Expected STOP_MARKET, got {ref.order_type}"
        assert ref.stop_price == 2955.19
        assert ref.close_position is True

    def test_reconcile_snapshot_preserves_take_profit_market_type(self, order_index):
        """Verify TAKE_PROFIT_MARKET order type is preserved."""
        symbol = "ETHUSDT"

        snapshot_orders = [
            {
                "orderId": "12346",
                "clientOrderId": "AUR-ETHUSDT-L-TP-C0-abc123",
                "symbol": symbol,
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "origType": "TAKE_PROFIT_MARKET",
                "origQty": "0.088",
                "executedQty": "0",
                "price": "0",
                "stopPrice": "3136.13",
                "status": "NEW",
                "reduceOnly": False,
                "closePosition": True,
                "time": 1733161440000,
            }
        ]

        order_index.reconcile_snapshot(symbol, snapshot_orders)

        refs = order_index.get_by_symbol(symbol)
        assert len(refs) == 1

        ref = refs[0]
        assert ref.order_type == "TAKE_PROFIT_MARKET", f"Expected TAKE_PROFIT_MARKET, got {ref.order_type}"

    def test_reconcile_snapshot_both_brackets(self, order_index):
        """Verify both SL and TP brackets are correctly stored and retrievable."""
        symbol = "ETHUSDT"

        snapshot_orders = [
            {
                "orderId": "12345",
                "clientOrderId": "AUR-ETHUSDT-L-SL-C0-abc123",
                "symbol": symbol,
                "side": "SELL",
                "type": "STOP_MARKET",
                "origQty": "0.088",
                "stopPrice": "2955.19",
                "status": "NEW",
                "closePosition": True,
                "time": 1733161440000,
            },
            {
                "orderId": "12346",
                "clientOrderId": "AUR-ETHUSDT-L-TP-C0-abc123",
                "symbol": symbol,
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "origQty": "0.088",
                "stopPrice": "3136.13",
                "status": "NEW",
                "closePosition": True,
                "time": 1733161441000,
            }
        ]

        order_index.reconcile_snapshot(symbol, snapshot_orders)

        refs = order_index.get_by_symbol(symbol)
        assert len(refs) == 2

        types = {ref.order_type for ref in refs}
        assert "STOP_MARKET" in types, f"STOP_MARKET missing, got {types}"
        assert "TAKE_PROFIT_MARKET" in types, f"TAKE_PROFIT_MARKET missing, got {types}"

    def test_normalize_orders_from_reconciled_index(self, order_index):
        """Verify normalize_orders correctly converts reconciled OrderRefs to OrderViews."""
        symbol = "ETHUSDT"

        snapshot_orders = [
            {
                "orderId": "12345",
                "clientOrderId": "AUR-ETHUSDT-L-SL-C0-abc123",
                "symbol": symbol,
                "side": "SELL",
                "type": "STOP_MARKET",
                "origQty": "0.088",
                "stopPrice": "2955.19",
                "status": "NEW",
                "closePosition": True,
                "time": 1733161440000,
            },
            {
                "orderId": "12346",
                "clientOrderId": "AUR-ETHUSDT-L-TP-C0-abc123",
                "symbol": symbol,
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "origQty": "0.088",
                "stopPrice": "3136.13",
                "status": "NEW",
                "closePosition": True,
                "time": 1733161441000,
            }
        ]

        order_index.reconcile_snapshot(symbol, snapshot_orders)

        # This is what runtime._get_order_views does
        refs = order_index.get_by_symbol(symbol)
        raw_orders = [r.to_dict() for r in refs]
        order_views = normalize_orders(raw_orders)

        assert len(order_views) == 2

        sl_views = [v for v in order_views if v.order_type == "STOP_MARKET"]
        tp_views = [v for v in order_views if v.order_type ==
                    "TAKE_PROFIT_MARKET"]

        assert len(sl_views) == 1, f"Expected 1 SL view, got {len(sl_views)}"
        assert len(tp_views) == 1, f"Expected 1 TP view, got {len(tp_views)}"

    def test_order_snapshot_is_active(self, order_index):
        """Verify order with status=NEW is considered active for bracket detection."""
        from apps.reference.domains.execution_position.aggregator_oco.contracts import OrderSnapshot
        from apps.reference.domains.execution_position.aggregator_oco.engine import _view_to_order_snapshot
        from decimal import Decimal

        symbol = "ETHUSDT"

        snapshot_orders = [
            {
                "orderId": "12345",
                "clientOrderId": "AUR-ETHUSDT-L-SL-C0-abc123",
                "symbol": symbol,
                "side": "SELL",
                "type": "STOP_MARKET",
                "origQty": "0.088",
                "stopPrice": "2955.19",
                "status": "NEW",
                "closePosition": True,
                "time": 1733161440000,
            },
        ]

        order_index.reconcile_snapshot(symbol, snapshot_orders)

        refs = order_index.get_by_symbol(symbol)
        raw_orders = [r.to_dict() for r in refs]
        order_views = normalize_orders(raw_orders)

        assert len(order_views) == 1
        view = order_views[0]

        # Convert to OrderSnapshot (what AggregatorInput uses)
        snapshot = _view_to_order_snapshot(view)

        assert snapshot.type == "STOP_MARKET"
        assert snapshot.status == "NEW"
        assert snapshot.is_stop_loss() is True, "Should be recognized as SL"
        assert snapshot.is_active() is True, "NEW status should be active"


class TestBracketDetectionEndToEnd:
    """End-to-end test for bracket detection after snapshot reconciliation."""

    def test_get_active_sl_after_reconcile(self):
        """Verify get_active_sl finds SL order after snapshot reconciliation."""
        from apps.reference.domains.execution_position.aggregator_oco.contracts import (
            AggregatorInput,
            PositionSnapshot,
        )
        from apps.reference.domains.execution_position.aggregator_oco.engine import (
            _view_to_order_snapshot,
        )
        from decimal import Decimal

        order_index = OrderIndex(ttl_sec=3600)
        symbol = "ETHUSDT"

        # Simulated Binance snapshot with SL and TP
        snapshot_orders = [
            {
                "orderId": "12345",
                "clientOrderId": "AUR-ETHUSDT-L-SL-C0-abc123",
                "symbol": symbol,
                "side": "SELL",
                "type": "STOP_MARKET",
                "origQty": "0.088",
                "stopPrice": "2955.19",
                "status": "NEW",
                "closePosition": True,
                "time": 1733161440000,
            },
            {
                "orderId": "12346",
                "clientOrderId": "AUR-ETHUSDT-L-TP-C0-abc123",
                "symbol": symbol,
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "origQty": "0.088",
                "stopPrice": "3136.13",
                "status": "NEW",
                "closePosition": True,
                "time": 1733161441000,
            }
        ]

        # Reconcile snapshot
        order_index.reconcile_snapshot(symbol, snapshot_orders)

        # Get order views (what runtime does)
        refs = order_index.get_by_symbol(symbol)
        raw_orders = [r.to_dict() for r in refs]
        order_views = normalize_orders(raw_orders)

        # Convert to OrderSnapshots
        order_snapshots = [_view_to_order_snapshot(v) for v in order_views]

        # Build AggregatorInput
        position = PositionSnapshot(
            symbol=symbol,
            side="LONG",
            qty=Decimal("0.088"),
            entry_price=Decimal("3010.0"),
        )

        agg_input = AggregatorInput(
            symbol=symbol,
            position=position,
            orders=order_snapshots,
        )

        # Verify bracket detection
        active_sl = agg_input.get_active_sl()
        active_tp = agg_input.get_active_tp()

        assert active_sl is not None, "SL order should be detected"
        assert active_tp is not None, "TP order should be detected"

        assert active_sl.is_stop_loss() is True
        assert active_tp.is_take_profit() is True

    def test_engine_noop_when_brackets_exist(self):
        """Verify engine returns NOOP plan when both brackets already exist."""
        from apps.reference.domains.execution_position.aggregator_oco.engine import (
            compute_bracket_plan_from_raw,
        )
        from decimal import Decimal

        symbol = "ETHUSDT"

        # Existing brackets on exchange
        existing_orders = [
            {
                "order_id": "12345",
                "side": "SELL",
                "type": "STOP_MARKET",
                "stop_price": "2955.19",
                "status": "NEW",
            },
            {
                "order_id": "12346",
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "stop_price": "3136.13",
                "status": "NEW",
            }
        ]

        plan = compute_bracket_plan_from_raw(
            symbol=symbol,
            position_side="LONG",
            position_qty=Decimal("0.088"),
            entry_price=Decimal("3010.0"),
            orders=existing_orders,
            sl_pct=Decimal("0.0175"),  # 1.75%
            tp_rr=Decimal("1.4286"),
        )

        # Should NOT have PLACE actions when brackets already exist
        place_actions = [a for a in plan.actions if a.action in (
            "PLACE_SL", "PLACE_TP")]
        assert len(
            place_actions) == 0, f"Should not PLACE when brackets exist, got: {[a.action for a in plan.actions]}"
