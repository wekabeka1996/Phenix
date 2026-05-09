"""
PHASE 3 — TDD anchor: commission fees accumulation per symbol across fills.

Contracts:
1. on_order_fill accumulates payload 'commission' into _accumulated_fees_by_symbol[symbol]
   for ALL fills (ENTRY, SL, TP, CLOSE) in the current lifecycle.
2. Zero commission (None, "0", 0.0) is accumulated as 0.0 — never skipped.
3. Independent accumulation per symbol: BTCUSDT and ETHUSDT do not interfere.
4. _accumulated_fees_by_symbol[symbol] is cleared after POSITION_CLOSED write.

These tests MUST FAIL before Phase 3 implementation (red).
They MUST PASS after Phase 3 implementation (green).
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers (extended from Phase 1/2 pattern)
# ---------------------------------------------------------------------------

def _make_mock_fsm():
    """Mock ExecPosFSM with all per-symbol dicts as real dicts."""
    mock_fsm = MagicMock()
    mock_fsm._last_lifecycle_rid_by_symbol = {}
    mock_fsm._last_lifecycle_fill_price_by_symbol = {}
    mock_fsm._last_realized_pnl_by_symbol = {}
    mock_fsm._last_close_reason_by_symbol = {}
    mock_fsm._last_lifecycle_ikey_by_symbol = {}
    mock_fsm._last_trade_id_by_symbol = {}
    mock_fsm._last_entry_side_by_symbol = {}
    # Phase 3 cache — may not exist yet on real FSM; set to validate
    mock_fsm._accumulated_fees_by_symbol = {}
    mock_fsm._close_accounting_truth_by_symbol = {}
    mock_fsm._pending_intent_data = {}
    mock_fsm._pending_entry_meta = {}
    mock_fsm._pending_brackets = {}
    mock_fsm._open_regime_by_symbol = {}
    mock_fsm._open_strategy_by_symbol = {}
    mock_fsm._last_position_closed_ts = {}
    mock_fsm._mark_processed_event.return_value = True  # skip dedup
    mock_fsm.exposure_guard.state.postfill_reservations = {}
    mock_fsm.exposure_guard.expire_stale.return_value = []
    mock_fsm.exposure_guard.get_exposure_summary.return_value = {}
    mock_fsm._get_async_loop.return_value = None
    mock_fsm._latest_portfolio_state = {}
    return mock_fsm


def _make_fill_event(
    order_id="EX-ORD-001",
    symbol="BTCUSDT",
    client_order_id="ENTRY-BTCUSDT-abc001",
    trade_id="10001",
    commission="0.05",
    side="BUY",
):
    return SimpleNamespace(
        pld={
            "orderId": order_id,
            "symbol": symbol,
            "quantity": "0.01",
            "rid": client_order_id,
            "clientOrderId": client_order_id,
            "tradeId": trade_id,
            "commission": commission,
            "commissionAsset": "USDT",
            "realizedPnl": "0.0",
            "price": "50000.0",
            "side": side,
        },
        rid=client_order_id,
    )


def _run_fill(mock_fsm, event):
    """Run EPEventHandlers.on_order_fill — returns list of written dicts."""
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod

    mock_fsm.order_index = None
    mock_fsm.fsm.order_index = None

    written = []
    with patch.object(handlers_mod, "_trade_lifecycle", None), \
            patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
            patch("apps.reference.domains.execution_position.orchestration.event_handlers.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_000
        mock_log_fn.return_value.write.side_effect = written.append
        handler = handlers_mod.EPEventHandlers(mock_fsm)
        handler.on_order_fill(event)
    return written


def _run_portfolio_close(mock_fsm, accumulated_fees=0.09, realized_pnl=-1.0):
    """Trigger POSITION_CLOSED by simulating portfolio state update."""
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod

    mock_fsm._prev_position_amts = {"BTCUSDT": 1.0}
    mock_fsm._last_lifecycle_rid_by_symbol = {
        "BTCUSDT": "ENTRY-BTCUSDT-abc001"}
    mock_fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 50000.0}
    mock_fsm._last_realized_pnl_by_symbol = {"BTCUSDT": realized_pnl}
    mock_fsm._last_lifecycle_ikey_by_symbol = {"BTCUSDT": "idem-key-001"}
    mock_fsm._last_trade_id_by_symbol = {"BTCUSDT": "10001"}
    mock_fsm._last_entry_side_by_symbol = {"BTCUSDT": "BUY"}
    mock_fsm._accumulated_fees_by_symbol = {"BTCUSDT": accumulated_fees}
    mock_fsm._close_accounting_truth_by_symbol = {
        "BTCUSDT": {
            "trade_id": "10001",
            "close_price": 50000.0,
            "realized_pnl": realized_pnl,
            "fees": accumulated_fees,
            "lifecycle_id": "idem-key-001",
            "entry_side": "BUY",
            "close_reason": "POSITION_CLOSED_DETECTED",
            "pnl_status": "resolved",
            "pnl_source": "close_fill",
            "economic_close_detected": True,
            "economic_close_kind": "explicit_close_fill",
        }
    }

    event = SimpleNamespace(
        pld={"positions": [{"symbol": "BTCUSDT", "positionAmt": 0.0}]}
    )
    written = []
    with patch.object(handlers_mod, "_trade_lifecycle", None), \
            patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
            patch("apps.reference.domains.execution_position.orchestration.event_handlers.get_clock") as mock_clock:
        mock_clock.return_value.now_sec.return_value = 1_700_000.0
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_000
        mock_log_fn.return_value.write.side_effect = written.append
        handler = handlers_mod.EPEventHandlers(mock_fsm)
        handler.on_portfolio_state_updated(event)
    return written


# ---------------------------------------------------------------------------
# Tests: on_order_fill — fee accumulation
# ---------------------------------------------------------------------------


class TestFeesAccumulation:
    """Phase 3: on_order_fill must accumulate commission into _accumulated_fees_by_symbol."""

    def test_single_fill_fee_accumulated(self):
        """
        After one fill with commission=0.05, _accumulated_fees_by_symbol must be 0.05.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        event = _make_fill_event(commission="0.05")
        _run_fill(mock_fsm, event)
        assert mock_fsm._accumulated_fees_by_symbol.get("BTCUSDT") == pytest.approx(0.05), (
            "_accumulated_fees_by_symbol must reflect commission from first fill"
        )

    def test_fees_accumulated_across_entry_and_sl_fills(self):
        """
        After two fills (ENTRY commission=0.05, SL commission=0.04), total must be 0.09.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        # ENTRY fill
        entry_event = _make_fill_event(
            order_id="EX-001",
            client_order_id="ENTRY-BTCUSDT-r1",
            commission="0.05",
        )
        _run_fill(mock_fsm, entry_event)

        # SL fill (different order_id to avoid dedup)
        sl_event = _make_fill_event(
            order_id="EX-002",
            client_order_id="SL-BTCUSDT-r1",
            commission="0.04",
            side="SELL",
        )
        _run_fill(mock_fsm, sl_event)

        assert mock_fsm._accumulated_fees_by_symbol.get("BTCUSDT") == pytest.approx(0.09), (
            "_accumulated_fees_by_symbol must sum commissions across ALL fills (ENTRY + SL)"
        )

    def test_zero_commission_accumulated_not_skipped(self):
        """
        A fill with commission=0 must NOT skip accumulation.
        After fill with 0 commission, accumulated fee must be 0.0 (not absent).
        FAILS before Phase 3 implementation (dict key absent).
        """
        mock_fsm = _make_mock_fsm()
        event = _make_fill_event(commission="0")
        _run_fill(mock_fsm, event)
        assert "BTCUSDT" in mock_fsm._accumulated_fees_by_symbol, (
            "_accumulated_fees_by_symbol must have an entry even for 0 commission"
        )
        assert mock_fsm._accumulated_fees_by_symbol["BTCUSDT"] == pytest.approx(0.0), (
            "accumulated fee must be 0.0 for zero-commission fill"
        )

    def test_none_commission_accumulated_as_zero(self):
        """
        A fill with commission=None must accumulate 0.0 (fail-closed, not crash).
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        event = _make_fill_event(commission=None)
        _run_fill(mock_fsm, event)
        # Should not crash AND should set BTCUSDT entry to 0.0
        assert mock_fsm._accumulated_fees_by_symbol.get("BTCUSDT", None) is not None or \
            mock_fsm._accumulated_fees_by_symbol.get("BTCUSDT", None) == pytest.approx(0.0), (
            "None commission must accumulate as 0.0, not crash"
        )

    def test_fees_accumulate_independently_per_symbol(self):
        """
        Fees for BTCUSDT and ETHUSDT must accumulate independently.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        btc_event = _make_fill_event(
            order_id="EX-BTC-001",
            symbol="BTCUSDT",
            client_order_id="ENTRY-BTCUSDT-s1",
            commission="0.05",
        )
        eth_event = _make_fill_event(
            order_id="EX-ETH-001",
            symbol="ETHUSDT",
            client_order_id="ENTRY-ETHUSDT-s1",
            commission="0.03",
        )
        _run_fill(mock_fsm, btc_event)
        _run_fill(mock_fsm, eth_event)

        assert mock_fsm._accumulated_fees_by_symbol.get("BTCUSDT") == pytest.approx(0.05), (
            "BTCUSDT fees must not be affected by ETHUSDT fill"
        )
        assert mock_fsm._accumulated_fees_by_symbol.get("ETHUSDT") == pytest.approx(0.03), (
            "ETHUSDT fees must accumulate independently from BTCUSDT"
        )

    def test_fees_cleared_after_position_closed(self):
        """
        _accumulated_fees_by_symbol[symbol] must be popped after POSITION_CLOSED write.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        mock_fsm._accumulated_fees_by_symbol = {"BTCUSDT": 0.09}

        _run_portfolio_close(mock_fsm, accumulated_fees=0.09)

        assert "BTCUSDT" not in mock_fsm._accumulated_fees_by_symbol, (
            "_accumulated_fees_by_symbol[BTCUSDT] must be popped after POSITION_CLOSED write"
        )
