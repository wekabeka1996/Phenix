from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.adapters.watchdog import (
    OrderDeadline,
    OrderTimeoutType,
    OrderTimeoutWatchdog,
)


GLOBAL_TTL_MS = 1_800_000
OVERRIDE_TTL_MS = 1_200_000
PARTIAL_FILL_TS_MS = 50_000


def _make_watchdog(*, fill_ttl_ms: int = GLOBAL_TTL_MS) -> OrderTimeoutWatchdog:
    watchdog = OrderTimeoutWatchdog(
        ack_ttl_ms=8_000,
        fill_ttl_ms=fill_ttl_ms,
        check_interval_ms=1_000,
        rps_limit=10,
    )
    watchdog._enabled = False
    return watchdog


def _make_deadline(
    *,
    order_id: str = "order-1",
    client_order_id: str = "ENTRY-1",
    symbol: str = "ETHUSDT",
    override_ms: int | None = OVERRIDE_TTL_MS,
) -> OrderDeadline:
    return OrderDeadline(
        order_id=order_id,
        client_order_id=client_order_id,
        symbol=symbol,
        deadline_ms=10_000,
        timeout_type=OrderTimeoutType.FILL_TIMEOUT,
        rid="rid-1",
        side="sell",
        fill_ttl_override_ms=override_ms,
    )


def _make_event_handler_fsm(deadline: OrderDeadline) -> MagicMock:
    fsm = MagicMock()
    fsm._last_lifecycle_rid_by_symbol = {}
    fsm._last_lifecycle_fill_price_by_symbol = {}
    fsm._last_realized_pnl_by_symbol = {}
    fsm._last_close_reason_by_symbol = {}
    fsm._last_lifecycle_ikey_by_symbol = {}
    fsm._last_trade_id_by_symbol = {}
    fsm._last_entry_side_by_symbol = {}
    fsm._accumulated_fees_by_symbol = {}
    fsm._close_accounting_truth_by_symbol = {}
    fsm._pending_intent_data = {}
    fsm._pending_entry_meta = {deadline.order_id: {"idempotent_key": "idem-1"}}
    fsm._pending_brackets = {}
    fsm._open_regime_by_symbol = {}
    fsm._open_strategy_by_symbol = {}
    fsm._last_position_closed_ts = {}
    fsm._prev_position_amts = {}
    fsm._latest_portfolio_state = {}
    fsm.manage_flows = {}
    fsm._mark_processed_event.return_value = True
    fsm._get_async_loop.return_value = None

    exposure_guard = MagicMock()
    exposure_guard.state = SimpleNamespace(
        postfill_reservations={},
        pending_exposure={},
    )
    exposure_guard.record_postfill_hold.return_value = {
        "exp_ts": PARTIAL_FILL_TS_MS + GLOBAL_TTL_MS,
        "notional_source": "fill_payload",
    }
    exposure_guard.get_exposure_summary.return_value = {}
    exposure_guard.expire_stale.return_value = []
    fsm.exposure_guard = exposure_guard

    watchdog = _make_watchdog()
    watchdog.acked_orders[deadline.order_id] = deadline
    watchdog.on_order_fill = MagicMock(wraps=watchdog.on_order_fill)
    fsm.watchdog = watchdog

    fsm.config.domains.execution_position.order_lifecycle.fill_settlement_delay_ms = 100
    fsm.order_index = None
    fsm.fsm = SimpleNamespace(order_index=None)
    return fsm


def _make_fill_event(
    *,
    order_id: str,
    client_order_id: str,
    symbol: str = "ETHUSDT",
    status: str = "PARTIALLY_FILLED",
    quantity: str = "0.581",
    side: str = "SELL",
) -> SimpleNamespace:
    return SimpleNamespace(
        pld={
            "orderId": order_id,
            "symbol": symbol,
            "quantity": quantity,
            "status": status,
            "rid": "rid-1",
            "clientOrderId": client_order_id,
            "tradeId": "trade-1",
            "commission": "0.01",
            "commissionAsset": "USDT",
            "realizedPnl": "0.0",
            "price": "2500.0",
            "side": side,
        },
        rid="rid-1",
    )


def _run_event_handler_fill(fsm: MagicMock, event: SimpleNamespace, *, now_ms: int) -> None:
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod

    with patch.object(handlers_mod, "_trade_lifecycle", None), \
            patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
            patch("apps.reference.domains.execution_position.orchestration.event_handlers.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = now_ms
        mock_clock.return_value.now_sec.return_value = now_ms / 1000.0
        mock_log_fn.return_value.write = MagicMock()
        handlers_mod.EPEventHandlers(fsm).on_order_fill(event)


@pytest.mark.asyncio
async def test_rest_poll_partial_fill_preserves_override_ttl() -> None:
    watchdog = _make_watchdog()
    deadline = _make_deadline(order_id="order-rest-override")
    watchdog.acked_orders[deadline.order_id] = deadline
    watchdog.set_hooks(
        AsyncMock(
            return_value={
                "status": "PARTIALLY_FILLED",
                "executedQty": "0.581",
                "avgPrice": "2500.0",
                "clientOrderId": deadline.client_order_id,
                "side": "SELL",
            }
        ),
        AsyncMock(),
    )

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = PARTIAL_FILL_TS_MS
        await watchdog._poll_order_statuses()

    assert watchdog.acked_orders[deadline.order_id].deadline_ms == PARTIAL_FILL_TS_MS + OVERRIDE_TTL_MS


@pytest.mark.asyncio
async def test_rest_poll_partial_fill_without_override_uses_global_ttl() -> None:
    watchdog = _make_watchdog()
    deadline = _make_deadline(order_id="order-rest-global", override_ms=None)
    watchdog.acked_orders[deadline.order_id] = deadline
    watchdog.set_hooks(
        AsyncMock(
            return_value={
                "status": "PARTIALLY_FILLED",
                "executedQty": "0.581",
                "avgPrice": "2500.0",
                "clientOrderId": deadline.client_order_id,
                "side": "SELL",
            }
        ),
        AsyncMock(),
    )

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = PARTIAL_FILL_TS_MS
        await watchdog._poll_order_statuses()

    assert watchdog.acked_orders[deadline.order_id].deadline_ms == PARTIAL_FILL_TS_MS + GLOBAL_TTL_MS


def test_event_handler_partial_fill_preserves_override_ttl() -> None:
    deadline = _make_deadline(order_id="order-ws-override")
    fsm = _make_event_handler_fsm(deadline)

    _run_event_handler_fill(
        fsm,
        _make_fill_event(
            order_id=deadline.order_id,
            client_order_id=deadline.client_order_id,
            status="PARTIALLY_FILLED",
        ),
        now_ms=PARTIAL_FILL_TS_MS,
    )

    assert fsm.watchdog.acked_orders[deadline.order_id].deadline_ms == PARTIAL_FILL_TS_MS + OVERRIDE_TTL_MS


def test_rest_poll_partial_fill_keeps_order_tracked_until_terminal_fill() -> None:
    watchdog = _make_watchdog()
    deadline = _make_deadline(order_id="order-rest-retained")
    watchdog.acked_orders[deadline.order_id] = deadline

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = PARTIAL_FILL_TS_MS
        watchdog.acked_orders[deadline.order_id].deadline_ms = PARTIAL_FILL_TS_MS + \
            watchdog.fill_ttl_ms

    assert deadline.order_id in watchdog.acked_orders
    watchdog.on_order_fill(deadline.order_id)
    assert deadline.order_id not in watchdog.acked_orders


def test_event_handler_partial_fill_does_not_trigger_terminal_cleanup() -> None:
    deadline = _make_deadline(order_id="order-ws-nonterminal")
    fsm = _make_event_handler_fsm(deadline)

    _run_event_handler_fill(
        fsm,
        _make_fill_event(
            order_id=deadline.order_id,
            client_order_id=deadline.client_order_id,
            status="PARTIALLY_FILLED",
        ),
        now_ms=PARTIAL_FILL_TS_MS,
    )

    fsm.watchdog.on_order_fill.assert_not_called()
    assert deadline.order_id in fsm.watchdog.acked_orders


def test_event_handler_final_fill_still_deregisters() -> None:
    deadline = _make_deadline(order_id="order-ws-filled")
    fsm = _make_event_handler_fsm(deadline)

    _run_event_handler_fill(
        fsm,
        _make_fill_event(
            order_id=deadline.order_id,
            client_order_id=deadline.client_order_id,
            status="FILLED",
        ),
        now_ms=PARTIAL_FILL_TS_MS,
    )

    fsm.watchdog.on_order_fill.assert_called_once_with(deadline.order_id)
    assert deadline.order_id not in fsm.watchdog.acked_orders


@pytest.mark.asyncio
async def test_timeout_fires_at_override_horizon_after_partial_rearm() -> None:
    watchdog = _make_watchdog()
    deadline = _make_deadline(order_id="order-rca")
    watchdog.acked_orders[deadline.order_id] = deadline
    watchdog.set_hooks(
        AsyncMock(
            return_value={
                "status": "PARTIALLY_FILLED",
                "executedQty": "0.581",
                "avgPrice": "2500.0",
                "clientOrderId": deadline.client_order_id,
                "side": "SELL",
            }
        ),
        AsyncMock(),
    )

    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = PARTIAL_FILL_TS_MS
        await watchdog._poll_order_statuses()

    assert watchdog.acked_orders[deadline.order_id].deadline_ms < PARTIAL_FILL_TS_MS + GLOBAL_TTL_MS

    timeout_cb = MagicMock()
    watchdog.on_timeout_callback = timeout_cb
    watchdog.get_order_fn = None
    with patch("apps.reference.domains.execution_position.adapters.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = PARTIAL_FILL_TS_MS + OVERRIDE_TTL_MS + 1
        await watchdog._check_timeouts()

    timeout_cb.assert_called_once()
    assert deadline.order_id not in watchdog.acked_orders
