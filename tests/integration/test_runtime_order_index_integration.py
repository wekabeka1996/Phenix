import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.infra.order_index import OrderIndex

@pytest.mark.asyncio
class TestRuntimeOrderIndexIntegration:

    @pytest.fixture
    def mock_adapter(self):
        adapter = MagicMock()
        # ExecutionService calls create_order, not place_order
        adapter.create_order = AsyncMock(return_value={"orderId": "ord_123", "success": True})
        adapter.cancel_order = AsyncMock(return_value={"success": True})
        return adapter

    @pytest.fixture
    def runtime(self, mock_adapter):
        config = {"execution_position": {"enabled": True}}
        rt = ExecPosRuntimeV2(config, mock_adapter, price_service=MagicMock())
        # Mock gatekeeper to allow everything
        rt.gatekeeper = MagicMock()
        rt.gatekeeper.check_entry.return_value = {
            "allowed": True,
            "modified_params": {}
        }
        return rt

    async def test_entry_intent_updates_index(self, runtime):
        """Test that ENTRY_INTENT adds order to OrderIndex."""
        payload = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": 1.0,
            "price": 50000.0,
            "client_order_id": "cid_1",
            "rid": "rid_1"
        }

        # Fix: Pass symbol at top level
        await runtime.handle({"kind": "ENTRY_INTENT", "symbol": "BTCUSDT", "payload": payload})

        # Verify index updated
        ref = runtime.order_index.get(clientOrderId="cid_1")
        assert ref is not None
        assert ref.rid == "rid_1"
        assert ref.exchangeOrderId == "ord_123"
        assert ref.symbol == "BTCUSDT"
        assert ref.quantity == 1.0

    async def test_orders_snapshot_reconciliation(self, runtime):
        """Test that ORDERS_SNAPSHOT reconciles with OrderIndex."""
        # Pre-populate index with an order
        runtime.order_index.upsert_from_open(
            rid="rid_old",
            idempotent_key="idem_old",
            clientOrderId="cid_old",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT"
        )

        # Snapshot with ONE new order and ONE existing order
        snapshot = {
            "orders": [
                {
                    "symbol": "BTCUSDT",
                    "orderId": "ord_new",
                    "clientOrderId": "cid_new",
                    "side": "SELL",
                    "type": "LIMIT",
                    "price": "51000",
                    "origQty": "0.5",
                    "status": "NEW"
                },
                {
                    "symbol": "BTCUSDT",
                    "orderId": "ord_old_ex",
                    "clientOrderId": "cid_old", # Matches existing
                    "side": "BUY",
                    "type": "LIMIT",
                    "price": "50000",
                    "origQty": "1.0",
                    "status": "FILLED"
                }
            ]
        }

        await runtime.handle({"kind": "ORDERS_SNAPSHOT", "payload": snapshot})

        # Verify existing order updated
        ref_old = runtime.order_index.get(clientOrderId="cid_old")
        assert ref_old is not None
        assert ref_old.exchangeOrderId == "ord_old_ex"
        assert ref_old.status == "FILLED"

        # Verify new order created
        ref_new = runtime.order_index.get(clientOrderId="cid_new")
        assert ref_new is not None
        assert ref_new.exchangeOrderId == "ord_new"
        assert ref_new.symbol == "BTCUSDT"

        # Verify stale orders removed (if any were stale)
        # In this case, rid_old matched cid_old, so it should persist.

    async def test_cancel_intent_updates_index(self, runtime):
        """Test that CANCEL_INTENT marks order terminal in index."""
        # Setup order
        runtime.order_index.upsert_from_open(
            rid="rid_1",
            idempotent_key="idem_1",
            clientOrderId="cid_1",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT"
        )
        runtime.order_index.attach_exchange_id(clientOrderId="cid_1", exchangeOrderId="ord_1")

        await runtime.handle({"kind": "CANCEL_INTENT", "payload": {"order_id": "ord_1"}, "symbol": "BTCUSDT"})

        # Verify terminal (and expired/removed)
        ref = runtime.order_index.get(exchangeOrderId="ord_1")
        # Since _remove_order_from_mirror calls expire(), it might be gone if TTL is short or logic removes it.
        # Logic: mark_terminal -> expire. expire removes terminal orders.
        assert ref is None

    async def test_get_order_views_uses_index(self, runtime):
        """Test that _get_order_views retrieves from index."""
        runtime.order_index.upsert_from_open(
            rid="rid_1",
            idempotent_key="idem_1",
            clientOrderId="cid_1",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity=1.0,
            price=50000.0
        )

        views = runtime._get_order_views("BTCUSDT")
        assert len(views) == 1
        assert views[0].client_order_id == "cid_1"
        assert views[0].qty == 1.0

