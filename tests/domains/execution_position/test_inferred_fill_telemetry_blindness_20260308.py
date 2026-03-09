from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vfoundation.core import FSMCore


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="Known vulnerability: REST-discovered fills stay inside ExecPosFSM and do not reach global telemetry/position tracking.",
    strict=False,
)
async def test_vector4_rest_discovered_fill_must_emit_global_trade_event_when_account_update_missing(
    fsm_config,
) -> None:
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    if hasattr(fsm_config, "domains") and hasattr(fsm_config.domains, "execution_position"):
        fsm_config.domains.execution_position.bracket_health_check = None

    fsm_config.binance_api.testnet.api_key = "k"
    fsm_config.binance_api.testnet.api_secret = "s"
    fsm_config.binance_api.testnet.rest_url = "https://testnet.binancefuture.com"

    order_id = "vector4-order-1"
    symbol = "BTCUSDT"

    adapter = MagicMock()
    adapter.base_url = "https://testnet.binancefuture.com"
    adapter.get_order = AsyncMock(
        return_value={
            "status": "FILLED",
            "executedQty": "0.005",
            "avgPrice": "67013.00",
            "clientOrderId": "ENTRY-vector4",
            "side": "BUY",
        }
    )

    bus = FSMCore()
    observed: list[object] = []
    bus.listen("EVT:TRADE_EXECUTED", lambda msg: observed.append(msg))
    bus.listen("EVT:ORDER_FILL", lambda msg: observed.append(msg))

    with patch("apps.reference.domains.execution_position.fsm.BinanceAdapter", return_value=adapter), \
            patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as guardian_cls:
        guardian_cls.return_value = MagicMock()
        execpos = ExecPosFSM(config=fsm_config, fsm=bus, shadow_mode=False)

    execpos.watchdog.track_order_placed(order_id, "ENTRY-vector4", symbol)
    execpos.watchdog.on_order_ack(order_id)

    await execpos.watchdog._poll_order_statuses()

    execpos.watchdog.stop()

    assert observed, "Expected a deterministic global fill/execution event for downstream telemetry."
