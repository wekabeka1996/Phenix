import pytest
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from decimal import Decimal
import time
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter
from apps.reference.domains.execution_position.algo_order_index import AlgoOrderIndex, AlgoOrderUpdate


@pytest.mark.asyncio
class TestAlgoServiceLifecycle:

    @pytest.fixture
    def adapter(self):
        adapter = BinanceExecutionAdapter(
            config={"execution": {"use_algo_service_for_conditionals": True}}
        )
        adapter.api_key = "test_key"
        adapter.api_secret = "test_secret"
        adapter.algo_order_index = AlgoOrderIndex()
        adapter.fsm_core = MagicMock()
        return adapter

    async def test_algo_sl_tp_full_lifecycle(self, adapter):
        """
        Scenario 1: Open Position -> Place Algo SL/TP -> Algo Update (Filled) -> Closed
        """
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # 1. Place Algo Order (SL)
            # Mock response for POST /fapi/v1/algoOrder
            mock_response_place = MagicMock()
            mock_response_place.is_success = True
            mock_response_place.json.return_value = {
                "algoId": 1001,
                "clientAlgoOrderId": "SL_BTC_1",
                "code": 200,
                "msg": "success"
            }
            mock_client.post.return_value = mock_response_place

            result = await adapter._place_conditional_via_algo_service(
                symbol="BTCUSDT",
                side="SELL",
                quantity="1.0",
                order_type="STOP_MARKET",
                stop_price="49000",
                reduce_only=True,
                idempotent_key="SL_BTC_1",
                time_in_force="GTC"
            )

            assert result["orderId"] == 1001
            assert adapter.algo_order_index.get_by_client_id(
                "SL_BTC_1") is not None
            assert adapter.algo_order_index.get_by_client_id(
                "SL_BTC_1").status == "NEW"

            # 2. Simulate ALGO_UPDATE (FILLED) via WebSocket
            update_msg = {
                "e": "ALGO_UPDATE",
                "s": "BTCUSDT",
                "a": {
                    "c": "SL_BTC_1",
                    "i": 1001,
                    "s": "FILLED",
                    "S": "SELL",
                    "o": "STOP_MARKET",
                    "l": "1.0",
                    "z": "1.0",
                    "E": int(time.time() * 1000)
                }
            }
            adapter._handle_algo_update(update_msg)

            # Verify state updated
            algo_order = adapter.algo_order_index.get_by_client_id("SL_BTC_1")
            assert algo_order.status == "FILLED"
            assert algo_order.cumulative_filled_qty == Decimal("1.0")

            # Verify event emitted
            adapter.fsm_core.emit.assert_called_with(
                "EVT:ALGO_ORDER_UPDATED",
                ANY,
                "WS_ALGO_UPDATE"
            )

    async def test_algo_cancel_flow(self, adapter):
        """
        Scenario 2: Open Algo Order -> Cancel -> Idempotent Cancel
        """
        # Pre-populate index with an active order
        adapter.algo_order_index.register_new_algo_order(
            client_algo_order_id="TP_ETH_1",
            algo_order_id="2002",
            symbol="ETHUSDT",
            side="SELL",
            algo_type="TAKE_PROFIT_MARKET",
            quantity=Decimal("10.0"),
            reduce_only=True
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # 1. Cancel Order
            mock_response_cancel = MagicMock()
            mock_response_cancel.is_success = True
            mock_response_cancel.json.return_value = {
                "algoId": 2002, "status": "CANCELED"}
            mock_client.delete.return_value = mock_response_cancel

            # Call generic cancel, should route to algo service
            result = await adapter._cancel_binance_order_async("ETHUSDT", "2002")

            assert result["status"] == "CANCELED"
            mock_client.delete.assert_called()
            # Verify URL was algoOrder
            args, kwargs = mock_client.delete.call_args
            assert "/fapi/v1/algoOrder" in args[0]

            # 2. Idempotent Cancel (Simulate -2011)
            mock_response_fail = MagicMock()
            mock_response_fail.is_success = False
            mock_response_fail.json.return_value = {
                "code": -2011, "msg": "Unknown order"}
            mock_client.delete.return_value = mock_response_fail

            result_retry = await adapter._cancel_binance_order_async("ETHUSDT", "2002")

            # Should return success due to idempotency wrapper in _cancel_conditional_via_algo_service
            assert result_retry["status"] == "CANCELED"
            assert result_retry["code"] == 200

    async def test_restart_with_open_algo_orders_snapshot(self, adapter):
        """
        Scenario 3: Restart -> Load Snapshot -> Consistent State
        """
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # Mock GET /fapi/v1/openAlgoOrders
            mock_response_snapshot = MagicMock()
            mock_response_snapshot.is_success = True
            mock_response_snapshot.json.return_value = {
                "orders": [
                    {
                        "algoId": 3003,
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "type": "STOP_MARKET",
                        "origQty": "0.5",
                        "stopPrice": "48000",
                        "clientAlgoOrderId": "EXISTING_SL",
                        "reduceOnly": True
                    }
                ]
            }
            mock_client.get.return_value = mock_response_snapshot

            # Execute Snapshot Load
            orders = await adapter.load_open_algo_orders_snapshot()

            assert len(orders) == 1

            # Verify Index Populated
            algo_order = adapter.algo_order_index.get_by_algo_id("3003")
            assert algo_order is not None
            assert algo_order.client_algo_order_id == "EXISTING_SL"
            assert algo_order.trigger_price == Decimal("48000")

    async def test_audit_consistency(self, adapter):
        """
        Scenario 4: Audit Consistency Check
        """
        # Local: Has ID 100
        adapter.algo_order_index.register_new_algo_order(
            client_algo_order_id="LOCAL_ONLY",
            algo_order_id="100",
            symbol="BTCUSDT",
            side="BUY",
            algo_type="STOP",
            quantity=Decimal("1")
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # Remote: Has ID 200 (Missing Local)
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_response.json.return_value = {
                "orders": [
                    {"algoId": 200, "symbol": "BTCUSDT"}
                ]
            }
            mock_client.get.return_value = mock_response

            report = await adapter.audit_algo_orders_consistency("BTCUSDT")

            assert report["is_consistent"] is False
            assert "100" in report["missing_remote"]
            assert "200" in report["missing_local"]
