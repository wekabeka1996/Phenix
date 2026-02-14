import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from vfoundation.core import FSMCore


@pytest.mark.asyncio
async def test_watchdog_polling_fill_triggers_deferred_brackets(fsm_config):
    """
    Regression: REST polling detects fill (WebSocket missed), but deferred LIMIT brackets
    were never placed because the watchdog->ExecPosFSM delivery path was broken.
    """
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    # Force non-shadow mode so ExecPosFSM wires watchdog hooks to adapter.get_order.
    fsm_config.binance_api.testnet.api_key = "k"
    fsm_config.binance_api.testnet.api_secret = "s"
    fsm_config.binance_api.testnet.rest_url = "https://testnet.binancefuture.com"

    order_id = "O-1"
    symbol = "BTCUSDT"

    adapter = MagicMock()
    adapter.base_url = "https://testnet.binancefuture.com"
    adapter.get_order = AsyncMock(
        return_value={
            "status": "FILLED",
            "executedQty": "0.005",
            "avgPrice": "67013.00",
            "clientOrderId": "ENTRY-357439f687e9",
        }
    )

    with patch("apps.reference.domains.execution_position.fsm.BinanceAdapter", return_value=adapter), \
         patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        mock_guardian_cls.return_value = MagicMock()

        fsm = FSMCore()
        execpos = ExecPosFSM(config=fsm_config, fsm=fsm, shadow_mode=False)

    # Prepare deferred bracket state for this LIMIT entry.
    execpos._pending_brackets[order_id] = {
        "symbol": symbol,
        "side": "BUY",
        "sl": "66677.9",
        "tp": "67515.7",
        "qty": 0.005,
        "rid": "r1",
        "idem_key": "idem1",
        "tick_size": "0.1",
        "corr_id": "c1",
        "oco_group_id": "g1",
        "entry_client_order_id": "ENTRY-357439f687e9",
        "created_at": 0.0,
    }
    execpos.correlation_store.put_entry_ack(
        order_id,
        {"corr_id": "c1", "oco_group_id": "g1", "rid": "r1", "parent_client_order_id": None},
    )

    # Patch bracket placement to observe that it gets scheduled on fill.
    execpos._place_deferred_brackets = AsyncMock()

    # Track order in watchdog and force a poll.
    execpos.watchdog.track_order_placed(order_id, "ENTRY-357439f687e9", symbol)
    execpos.watchdog.on_order_ack(order_id)

    await execpos.watchdog._poll_order_statuses()

    # The fill must be delivered into ExecPosFSM._on_order_fill, which should schedule bracket placement.
    execpos._place_deferred_brackets.assert_called_once()
    assert order_id not in execpos._pending_brackets
    assert order_id not in execpos.watchdog.acked_orders

    execpos.watchdog.stop()

