
import asyncio
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.config import ExecutionPositionConfig, AggregatedOcoConfig, SnapshotConfig, TrailingConfig, CloseConfig


def _make_runtime():
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(
            enabled=True, sl_pct=0.02, tp_rr=2.0),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(orders_ttl_sec=30.0, position_ttl_sec=30.0),
    )
    # Mock adapter
    adapter = MagicMock()
    adapter.create_order = AsyncMock(
        return_value={"orderId": 123, "success": True})
    adapter.cancel_order = AsyncMock(
        return_value={"orderId": 123, "success": True})

    rt = ExecPosRuntimeV2(config={}, adapter=adapter,
                          price_service=None, ep_config=ep_cfg)
    return rt


@pytest.mark.asyncio
async def test_concurrent_bracket_creation_unique_ids():
    runtime = _make_runtime()

    # Simulate 3 symbols trading at once
    symbols = ["SOLUSDT", "ETHUSDT", "BNBUSDT"]

    # Capture all create_order calls
    captured_ids = []

    async def mock_create_order(params=None, **kwargs):
        # Simulate network delay
        await asyncio.sleep(0.01)
        cid = params.client_order_id if params else kwargs.get(
            'client_order_id')
        if cid:
            captured_ids.append(cid)
        return {"orderId": int(time.time()*1000), "success": True, "clientOrderId": cid}

    runtime.execution_service.adapter.create_order = mock_create_order

    # Fire 3 trade events concurrently
    tasks = []
    for sym in symbols:
        payload = {
            "symbol": sym,
            "side": "BUY",
            "quantity": 1.0,  # Same qty to test collision if symbol ignored
            "price": 100.0,
            "status": "FILLED",
            "order_id": f"ORD_{sym}",
            "timestamp": time.time()
        }
        tasks.append(runtime.handle({
            "kind": "TRADE_EXECUTED",
            "symbol": sym,
            "payload": payload
        }))

    await asyncio.gather(*tasks)

    # Wait for brackets to be placed (they run async in _evaluate_brackets)
    await asyncio.sleep(0.5)

    print(f"Captured IDs: {captured_ids}")

    # Verify uniqueness
    assert len(captured_ids) > 0, "No brackets placed!"
    assert len(captured_ids) == len(set(captured_ids)
                                    ), "Duplicate ClientOrderIds detected!"

    # Verify format
    for cid in captured_ids:
        assert len(cid) <= 32, f"ID too long: {cid}"
        assert "AUR-" in cid
