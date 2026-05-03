import pytest
import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from vfoundation.core.protocol import Message

from apps.reference.domains.execution_position.guards.exposure_manager import ExposureManager
from apps.reference.core.time import get_clock


class MockFSM:
    def __init__(self, shadow_mode=False, loop=None):
        self.exposure_guard = MagicMock()
        self.exposure_guard.state = MagicMock()
        self.exposure_guard.state.pending_exposure = {}
        self.exposure_guard.state.postfill_reservations = {}
        self.exposure_guard.get_exposure_summary.return_value = {
            "mock": "summary"}

        self.adapter = AsyncMock()
        self.shadow_mode = shadow_mode
        self._loop = loop

        self._latest_portfolio_state = {
            "positions": [], "open_positions_usd": "100.0"}
        self._shadow_check_counter = 0
        self._pending_brackets = {}
        self._open_regime_by_symbol = {}
        self._supersede_canceling = set()
        self.watchdog = MagicMock()
        self.watchdog.pending_orders = {}
        self.watchdog.acked_orders = {}
        self._entry_mgr = MagicMock()

        self.config = MagicMock()
        self.config.domains.execution_position.shadow_check.enabled = True
        self.config.domains.execution_position.shadow_check.check_every_n_requests = 2
        self.config.domains.execution_position.shadow_check.use_absolute_for_large_portfolios = True
        self.config.domains.execution_position.shadow_check.large_portfolio_threshold_usd = 1000
        self.config.domains.execution_position.shadow_check.absolute_threshold_usd = 500
        self.config.domains.execution_position.shadow_check.tolerance_pct = 5.0

        self.metrics_collector = MagicMock()
        self.fsm = MagicMock()
        self.fsm.order_index = MagicMock()

    def _persist_restore_artifact_snapshot(self, trigger: str = "", allow_empty: bool = False) -> None:
        pass

    def _get_async_loop(self):
        return self._loop

    def _submit_async(self, coro, loop):
        asyncio.run_coroutine_threadsafe(coro, loop)


@pytest.fixture
def fsm():
    loop = asyncio.new_event_loop()
    fsm = MockFSM(loop=loop)
    yield fsm
    loop.close()


@pytest.fixture
def exposure_manager(fsm):
    return ExposureManager(fsm)


@patch("vfoundation.dr.wal.append")
def test_check_exposure_fail_closed_missing_fields(mock_wal, exposure_manager):
    msg = Message(op="DEC", verb="OPEN", src="src", dst="dst", pld={
                  "symbol": "BTCUSDT", "qty": 1.0})  # Missing price_ref
    result = exposure_manager.check_exposure_fail_closed(msg)
    assert result is None

    msg2 = Message(op="DEC", verb="OPEN", src="src", dst="dst", pld={})
    result2 = exposure_manager.check_exposure_fail_closed(msg2)
    assert result2 is None


@patch("vfoundation.dr.wal.append")
def test_check_exposure_fail_closed_missing_side(mock_wal, exposure_manager):
    msg = Message(op="DEC", verb="OPEN", src="src", dst="dst", pld={
                  "symbol": "BTCUSDT", "qty": 1.0, "price_ref": 50000})
    with pytest.raises(ValueError, match="Order side is missing"):
        exposure_manager.check_exposure_fail_closed(msg)


@patch("vfoundation.dr.wal.append")
def test_check_exposure_fail_closed_invalid_side(mock_wal, exposure_manager):
    msg = Message(op="DEC", verb="OPEN", src="src", dst="dst", pld={
                  "symbol": "BTCUSDT", "qty": 1.0, "price_ref": 50000, "side": "INVALID"})
    with pytest.raises(ValueError, match="Order side is invalid"):
        exposure_manager.check_exposure_fail_closed(msg)


@patch("vfoundation.dr.wal.append")
def test_check_exposure_fail_closed_blocked(mock_wal, exposure_manager, fsm):
    fsm.exposure_guard.can_open.return_value = {
        "allowed": False, "reason": "MAX_CAPITAL", "stale_sec": 10}
    msg = Message(op="DEC", verb="OPEN", src="src", dst="dst", rid="req1", pld={
        "symbol": "BTCUSDT", "qty": 1.0, "price_ref": 50000, "side": "BUY"
    })

    result = exposure_manager.check_exposure_fail_closed(msg)

    assert result is not None
    assert result.op == "ERR"
    assert result.verb == "OPEN"
    assert result.pld["reason"] == "MAX_CAPITAL"
    fsm.metrics_collector.record_exposure_fail_closed.assert_called_with(
        "MAX_CAPITAL")
    mock_wal.assert_called_once()


@patch("vfoundation.dr.wal.append")
def test_check_exposure_fail_closed_allowed_and_clipping(mock_wal, exposure_manager, fsm):
    fsm.exposure_guard.can_open.return_value = {"allowed": True}  # No clipping
    msg = Message(op="DEC", verb="OPEN", src="src", dst="dst", rid="req1", pld={
        "symbol": "BTCUSDT", "qty": 1.0, "price_ref": 50000, "side": "BUY", "idempotent_key": "res_1"
    })

    result = exposure_manager.check_exposure_fail_closed(msg)
    assert result is None
    fsm.exposure_guard.reserve.assert_called_with("res_1", Decimal(
        "50000.0"), reduce_only=False, symbol="BTCUSDT", side="BUY")

    # Test clipping
    fsm.exposure_guard.reset_mock()
    fsm.exposure_guard.can_open.return_value = {
        "allowed": True, "clipped_notional_abs": 25000}
    msg2 = Message(op="DEC", verb="OPEN", src="src", dst="dst", rid="req2", pld={
        "symbol": "BTCUSDT", "qty": 1.0, "price_ref": 50000, "side": "BUY", "idempotent_key": "res_2"
    })

    result2 = exposure_manager.check_exposure_fail_closed(msg2)
    assert result2 is None
    # 25000 / 50000 = 0.5
    assert Decimal(msg2.pld["qty"]) == Decimal("0.5")
    fsm.exposure_guard.reserve.assert_called_with("res_2", Decimal(
        "25000"), reduce_only=False, symbol="BTCUSDT", side="BUY")


@patch("vfoundation.dr.wal.append")
def test_check_exposure_fail_closed_shadow_check_trigger(mock_wal, exposure_manager, fsm):
    tasks = []
    def _capture_and_close(coro, loop):
        tasks.append(coro.cr_code.co_name)
        coro.close()
    fsm._submit_async = _capture_and_close
    fsm.exposure_guard.can_open.return_value = {"allowed": True}

    msg = Message(op="DEC", verb="OPEN", src="src", dst="dst", pld={
                  "symbol": "BTC", "qty": 1, "price_ref": 50000, "side": "BUY"})

    # Needs 2 requests to trigger (check_every_n_requests = 2)
    exposure_manager.check_exposure_fail_closed(msg)
    assert len(tasks) == 0
    assert fsm._shadow_check_counter == 1

    exposure_manager.check_exposure_fail_closed(msg)
    assert tasks == ["check_shadow_notional"]
    assert fsm._shadow_check_counter == 2


@patch("vfoundation.dr.wal.append")
def test_check_exposure_fail_closed_is_flip(mock_wal, exposure_manager, fsm):
    fsm._latest_portfolio_state = {
        "positions": [{"symbol": "BTCUSDT", "net_position": "-1.0"}]
    }
    fsm.exposure_guard.can_open.return_value = {"allowed": True}

    msg = Message(op="DEC", verb="OPEN", src="src", dst="dst", pld={
                  "symbol": "BTCUSDT", "qty": 0.5, "price_ref": 50000, "side": "BUY"})
    exposure_manager.check_exposure_fail_closed(msg)

    # Assert can_open called with is_flip=True and flip_fraction (DEF-E06: size-aware flip)
    # qty=0.5 against net_position=1.0 → flip_fraction = min(0.5,1.0)/1.0 = 0.5
    fsm.exposure_guard.can_open.assert_called_with("BTCUSDT", Decimal(
        "25000.0"), fsm._latest_portfolio_state, is_flip=True, flip_fraction=Decimal('0.5'))


@patch("vfoundation.dr.wal.append")
def test_check_exposure_fail_closed_exception(mock_wal, exposure_manager, fsm):
    fsm.exposure_guard.can_open.side_effect = Exception("General Error")
    msg = Message(op="DEC", verb="OPEN", src="src", dst="dst", pld={
                  "symbol": "BTCUSDT", "qty": 1.0, "price_ref": 50000, "side": "BUY"})

    result = exposure_manager.check_exposure_fail_closed(msg)
    assert result is not None
    assert result.op == "ERR"
    assert result.pld["reason"] == "EXPOSURE_CHECK_ERROR"
    mock_wal.assert_called_once()


@pytest.mark.asyncio
@patch("vfoundation.core.fsm_emit_compat.emit_compat", new_callable=AsyncMock)
async def test_check_shadow_notional(mock_emit, exposure_manager, fsm):
    # Test tolerance mismatch
    fsm._latest_portfolio_state["open_positions_usd"] = "100.0"
    fsm.adapter.get_positions_notional_usd_shadow.return_value = 110.0
    fsm.config.domains.execution_position.shadow_check.use_absolute_for_large_portfolios = False
    # 10 is > 5% mismatch
    fsm.config.domains.execution_position.shadow_check.tolerance_pct = 5.0

    await exposure_manager.check_shadow_notional()

    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][1].verb == "EXPOSURE_MISMATCH"

    # Test within tolerance
    mock_emit.reset_mock()
    fsm.adapter.get_positions_notional_usd_shadow.return_value = 104.0

    await exposure_manager.check_shadow_notional()
    mock_emit.assert_not_called()


@pytest.mark.asyncio
@patch("vfoundation.core.fsm_emit_compat.emit_compat", new_callable=AsyncMock)
async def test_check_shadow_notional_absolute_threshold(mock_emit, exposure_manager, fsm):
    # Large portfolio over absolute threshold
    fsm._latest_portfolio_state["open_positions_usd"] = "5000.0"
    fsm.adapter.get_positions_notional_usd_shadow.return_value = 5600.0
    # Absolute threshold is 500, diff is 600

    await exposure_manager.check_shadow_notional()
    mock_emit.assert_called_once()

    # Under absolute threshold
    mock_emit.reset_mock()
    fsm.adapter.get_positions_notional_usd_shadow.return_value = 5400.0

    await exposure_manager.check_shadow_notional()
    mock_emit.assert_not_called()


@patch("apps.reference.domains.execution_position.flows.manage.pending_brackets_wal.write_pending_brackets_cleared")
def test_handle_cancel_event(mock_wal, exposure_manager, fsm):
    tasks = []
    def _capture_and_close(coro, loop):
        tasks.append(coro.cr_code.co_name)
        coro.close()
    fsm._submit_async = _capture_and_close

    fsm._pending_brackets = {"o1": {"symbol": "BTCUSDT"}}
    fsm._supersede_canceling.add("BTCUSDT")
    fsm.watchdog.pending_orders = {}  # No more pending
    fsm.watchdog.acked_orders = {}

    msg = Message(op="EVT", verb="ORDER_CANCELLED", src="src", dst="dst", pld={
                  "order_id": "o1", "symbol": "BTCUSDT", "client_order_id": "c1"})

    exposure_manager.handle_cancel_event(msg)

    # 1. Clears bracket WAL
    mock_wal.assert_called_with(
        entry_order_id="o1", reason="cancelled", symbol="BTCUSDT")
    assert "o1" not in fsm._pending_brackets

    # 2. Marks order terminal
    fsm.fsm.order_index.get.assert_called_with(exchangeOrderId="o1")
    fsm.fsm.order_index.mark_terminal.assert_called_once()

    # 3. Emits exposure summary (async)
    assert tasks == ["emit_exposure_update_async"]

    # 4. Processes queued supersede
    fsm._entry_mgr.process_queued_supersede.assert_called_with("BTCUSDT")


def test_handle_cancel_event_supersede_wait(exposure_manager, fsm):
    fsm._supersede_canceling.add("BTCUSDT")
    # Dog still has another order pending for BTCUSDT
    mock_deadline = MagicMock()
    mock_deadline.symbol = "BTCUSDT"
    fsm.watchdog.pending_orders = {"o2": mock_deadline}

    msg = Message(op="EVT", verb="ORDER_CANCELLED", src="src",
                  dst="dst", pld={"order_id": "o1", "symbol": "BTCUSDT"})
    exposure_manager.handle_cancel_event(msg)

    fsm._entry_mgr.process_queued_supersede.assert_not_called()


@pytest.mark.asyncio
@patch("vfoundation.core.fsm_emit_compat.emit_compat", new_callable=AsyncMock)
async def test_emit_exposure_update_async(mock_emit, exposure_manager, fsm):
    msg = Message(op="EVT", verb="TEST", src="src", dst="dst")
    await exposure_manager.emit_exposure_update_async(msg)
    mock_emit.assert_called_once()
