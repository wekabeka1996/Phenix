import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from apps.reference.domains.execution_position.idempotent_cancel import (
    IdempotentCancelResult,
)


@pytest.mark.asyncio
async def test_do_cancel_logs_warning_on_failed_result(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    order_id = "ord_fail_1"
    deadline = SimpleNamespace(symbol=symbol, rid="rid_fail")

    fsm.watchdog = MagicMock()
    fsm.watchdog.pending_orders = {order_id: deadline}
    fsm.watchdog.acked_orders = {}
    fsm.adapter = MagicMock()
    fsm.shadow_mode = False
    fsm._cancel_order = AsyncMock(
        return_value=IdempotentCancelResult(
            success=False,
            reason="EXCEPTION_AFTER_2_RETRIES",
            is_idempotent_success=False,
        )
    )
    fsm._submit_async = MagicMock()

    with patch("apps.reference.domains.execution_position.fsm.order_logger.write") as write_mock, patch(
        "apps.reference.domains.execution_position.fsm.LOG.info"
    ) as info_mock, patch("apps.reference.domains.execution_position.fsm.LOG.warning") as warning_mock:
        fsm._cancel_pending_entries_for_symbol(
            symbol=symbol,
            reason="CANCEL_SUPERSEDED",
            context="test_ctx",
        )
        assert fsm._submit_async.call_count == 1
        await fsm._submit_async.call_args[0][0]

    warnings = [str(call.args[0]) for call in warning_mock.call_args_list if call.args]
    infos = [str(call.args[0]) for call in info_mock.call_args_list if call.args]

    assert any("Cancel FAILED" in msg for msg in warnings)
    assert not any("Cancelled pending entry" in msg for msg in infos)
    fsm.watchdog.on_order_cancel.assert_not_called()
    write_mock.assert_not_called()


@pytest.mark.asyncio
async def test_do_cancel_logs_success_on_success_result(fsm_harness):
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    order_id = "ord_ok_1"
    deadline = SimpleNamespace(symbol=symbol, rid="rid_ok")

    fsm.watchdog = MagicMock()
    fsm.watchdog.pending_orders = {order_id: deadline}
    fsm.watchdog.acked_orders = {}
    fsm.adapter = MagicMock()
    fsm.shadow_mode = False
    fsm._cancel_order = AsyncMock(
        return_value=IdempotentCancelResult(
            success=True,
            reason="CANCEL_SUCCESS",
            is_idempotent_success=True,
        )
    )
    fsm._submit_async = MagicMock()

    with patch("apps.reference.domains.execution_position.fsm.order_logger.write") as write_mock, patch(
        "apps.reference.domains.execution_position.fsm.LOG.info"
    ) as info_mock, patch("apps.reference.domains.execution_position.fsm.LOG.warning") as warning_mock:
        fsm._cancel_pending_entries_for_symbol(
            symbol=symbol,
            reason="CANCEL_SUPERSEDED",
            context="test_ctx",
        )
        assert fsm._submit_async.call_count == 1
        await fsm._submit_async.call_args[0][0]

    infos = [str(call.args[0]) for call in info_mock.call_args_list if call.args]
    warnings = [str(call.args[0]) for call in warning_mock.call_args_list if call.args]

    assert any("Cancelled pending entry" in msg for msg in infos)
    assert not any("Cancel FAILED" in msg for msg in warnings)
    fsm.watchdog.on_order_cancel.assert_called_once_with(order_id)
    write_mock.assert_called_once()
