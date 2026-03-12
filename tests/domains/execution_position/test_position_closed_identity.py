"""
PHASE 2 — TDD anchor: trade_id and entry side propagation in POSITION_CLOSED.

Contracts:
1. on_order_fill caches exchange tradeId into _last_trade_id_by_symbol[symbol].
2. on_order_fill caches ref.side into _last_entry_side_by_symbol[symbol] ONLY
   for ENTRY fills (clientOrderId prefix "ENTRY-").
3. SL/TP fills must NOT overwrite _last_entry_side_by_symbol.
4. POSITION_CLOSED write has top-level "trade_id" from cached tradeId.
5. POSITION_CLOSED write has "side" from cache (real BUY/SELL), not hardcoded "N/A".
6. Fail-closed: "side" falls back to "N/A" when cache empty (graceful, not crash).
7. Both caches cleared after POSITION_CLOSED write.

These tests MUST FAIL before Phase 2 implementation (red).
They MUST PASS after Phase 2 implementation (green).
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers (adapted from test_lifecycle_id_propagation.py Phase 1)
# ---------------------------------------------------------------------------

def _make_mock_fsm():
    """Mock ExecPosFSM with all per-symbol dicts as real dicts."""
    mock_fsm = MagicMock()
    mock_fsm._last_lifecycle_rid_by_symbol = {}
    mock_fsm._last_lifecycle_fill_price_by_symbol = {}
    mock_fsm._last_realized_pnl_by_symbol = {}
    mock_fsm._last_close_reason_by_symbol = {}
    mock_fsm._last_lifecycle_ikey_by_symbol = {}
    # Phase 2 caches — may not exist yet on real FSM; tests set to validate
    mock_fsm._last_trade_id_by_symbol = {}
    mock_fsm._last_entry_side_by_symbol = {}
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


def _make_order_fill_event(
    order_id="EX-ORD-002",
    symbol="BTCUSDT",
    qty="0.01",
    client_order_id="ENTRY-BTCUSDT-abc456",
    trade_id="99001",
    commission="0.05",
    side="BUY",
):
    return SimpleNamespace(
        pld={
            "orderId": order_id,
            "symbol": symbol,
            "quantity": qty,
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


def _make_order_index_mock(
    idempotent_key: str,
    side: str = "BUY",
    client_order_id: str = "ENTRY-BTCUSDT-abc456",
):
    """Return a mock OrderIndex that yields a ref with idempotent_key + side."""
    mock_ref = MagicMock()
    mock_ref.idempotent_key = idempotent_key
    mock_ref.side = side

    def mock_get(*, rid=None, clientOrderId=None, exchangeOrderId=None):
        if exchangeOrderId is not None:
            return None
        if clientOrderId == client_order_id:
            return mock_ref
        if rid == client_order_id:
            return mock_ref
        return None

    mock_oi = MagicMock()
    mock_oi.get.side_effect = mock_get
    return mock_oi, mock_ref


def _run_fill(mock_fsm, event, mock_oi=None):
    """
    Run EPEventHandlers.on_order_fill with patched order_logger.
    Returns list of dicts written to order_logger.
    """
    import apps.reference.domains.execution_position.event_handlers as handlers_mod

    # Explicitly set order_index to None so code falls through to mock_fsm.fsm.order_index
    mock_fsm.order_index = None
    if mock_oi is not None:
        mock_fsm.fsm.order_index = mock_oi
    else:
        mock_fsm.fsm.order_index = None

    written = []

    with patch.object(handlers_mod, "_trade_lifecycle", None), \
            patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
            patch("apps.reference.domains.execution_position.event_handlers.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_000
        mock_log_fn.return_value.write.side_effect = written.append

        handler = handlers_mod.EPEventHandlers(mock_fsm)
        handler.on_order_fill(event)

    return written


def _run_portfolio_close(
    mock_fsm,
    trade_id: str = "99001",
    entry_side: str = "BUY",
):
    """
    Run EPEventHandlers.on_portfolio_state_updated to trigger POSITION_CLOSED write.
    Pre-populates Phase 1 + Phase 2 caches. Returns list of dicts written to order_logger.
    """
    import apps.reference.domains.execution_position.event_handlers as handlers_mod

    mock_fsm._prev_position_amts = {"BTCUSDT": 1.0}
    mock_fsm._last_lifecycle_rid_by_symbol = {
        "BTCUSDT": "ENTRY-BTCUSDT-abc456"}
    mock_fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 50100.0}
    mock_fsm._last_realized_pnl_by_symbol = {"BTCUSDT": -0.5}
    mock_fsm._last_lifecycle_ikey_by_symbol = {
        "BTCUSDT": "test-idem-lifecycle-000"}
    # Phase 2 caches
    mock_fsm._last_trade_id_by_symbol = {"BTCUSDT": trade_id}
    mock_fsm._last_entry_side_by_symbol = {"BTCUSDT": entry_side}

    event = SimpleNamespace(
        pld={"positions": [{"symbol": "BTCUSDT", "positionAmt": 0.0}]}
    )

    written = []

    with patch.object(handlers_mod, "_trade_lifecycle", None), \
            patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
            patch("apps.reference.domains.execution_position.event_handlers.get_clock") as mock_clock:
        mock_clock.return_value.now_sec.return_value = 1_700_000.0
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_000
        mock_log_fn.return_value.write.side_effect = written.append

        handler = handlers_mod.EPEventHandlers(mock_fsm)
        handler.on_portfolio_state_updated(event)

    return written


# ---------------------------------------------------------------------------
# Tests: on_order_fill — trade_id and entry side caching
# ---------------------------------------------------------------------------


class TestOnOrderFillCaching:
    """Phase 2: on_order_fill must cache tradeId and (for ENTRY fills) ref.side."""

    def test_trade_id_cached_after_entry_fill(self):
        """
        After on_order_fill for ENTRY, _last_trade_id_by_symbol[symbol] must equal
        the tradeId from the payload.
        FAILS before Phase 2 implementation.
        """
        mock_fsm = _make_mock_fsm()
        mock_oi, _ = _make_order_index_mock("idem-001", side="BUY")
        event = _make_order_fill_event(
            trade_id="99001",
            client_order_id="ENTRY-BTCUSDT-abc456",
        )

        _run_fill(mock_fsm, event, mock_oi=mock_oi)

        assert mock_fsm._last_trade_id_by_symbol.get("BTCUSDT") == "99001", (
            "_last_trade_id_by_symbol must be set from payload tradeId"
        )

    def test_entry_side_cached_from_order_ref(self):
        """
        After on_order_fill for ENTRY, _last_entry_side_by_symbol[symbol] must equal
        ref.side from OrderIndex.
        FAILS before Phase 2 implementation.
        """
        mock_fsm = _make_mock_fsm()
        mock_oi, _ = _make_order_index_mock("idem-002", side="BUY")
        event = _make_order_fill_event(
            trade_id="99002",
            client_order_id="ENTRY-BTCUSDT-abc456",
            side="BUY",
        )

        _run_fill(mock_fsm, event, mock_oi=mock_oi)

        assert mock_fsm._last_entry_side_by_symbol.get("BTCUSDT") == "BUY", (
            "_last_entry_side_by_symbol must be set from OrderIndex ref.side for ENTRY fills"
        )

    def test_trade_id_updated_on_sl_fill(self):
        """
        SL/TP fills must still update _last_trade_id_by_symbol (every fill updates tradeId;
        the most-recent fill's tradeId wins).
        FAILS before Phase 2 implementation.
        """
        mock_fsm = _make_mock_fsm()
        # Prime with ENTRY fill first
        mock_oi_entry, _ = _make_order_index_mock(
            "idem-004", side="BUY", client_order_id="ENTRY-BTCUSDT-r1"
        )
        entry_event = _make_order_fill_event(
            trade_id="10001",
            client_order_id="ENTRY-BTCUSDT-r1",
        )
        _run_fill(mock_fsm, entry_event, mock_oi=mock_oi_entry)

        # SL fill with a different tradeId
        mock_oi_sl, _ = _make_order_index_mock(
            "idem-sl-004", side="SELL", client_order_id="SL-BTCUSDT-r1"
        )
        sl_event = _make_order_fill_event(
            order_id="EX-ORD-SL",
            client_order_id="SL-BTCUSDT-r1",
            trade_id="10002",
            side="SELL",
        )
        _run_fill(mock_fsm, sl_event, mock_oi=mock_oi_sl)

        assert mock_fsm._last_trade_id_by_symbol.get("BTCUSDT") == "10002", (
            "_last_trade_id_by_symbol must be updated on every fill (SL fill updates tradeId)"
        )

    def test_entry_side_not_overwritten_by_sl_fill(self):
        """
        SL fill must NOT overwrite _last_entry_side_by_symbol.
        Only ENTRY fills update the entry side cache.
        FAILS before Phase 2 implementation (when Phase 2 code incorrectly writes on all fills).
        Passes trivially before Phase 2 (no write code), but guards against regression.
        """
        mock_fsm = _make_mock_fsm()
        # Simulate prior ENTRY fill already primed the cache
        mock_fsm._last_entry_side_by_symbol["BTCUSDT"] = "BUY"

        # SL fill — side=SELL, order_kind=SL (clientOrderId prefix "SL-")
        mock_oi_sl, _ = _make_order_index_mock(
            "idem-sl-003", side="SELL", client_order_id="SL-BTCUSDT-r2"
        )
        sl_event = _make_order_fill_event(
            order_id="EX-ORD-003-SL",
            client_order_id="SL-BTCUSDT-r2",
            trade_id="88001",
            side="SELL",
        )
        _run_fill(mock_fsm, sl_event, mock_oi=mock_oi_sl)

        assert mock_fsm._last_entry_side_by_symbol.get("BTCUSDT") == "BUY", (
            "_last_entry_side_by_symbol must NOT be overwritten by SL fill"
        )


# ---------------------------------------------------------------------------
# Tests: POSITION_CLOSED — trade_id and real side emitted
# ---------------------------------------------------------------------------


class TestPositionClosedIdentity:
    """Phase 2: POSITION_CLOSED must carry real trade_id and entry side."""

    def test_position_closed_has_top_level_trade_id(self):
        """
        POSITION_CLOSED write dict must have a top-level 'trade_id' key.
        FAILS before Phase 2 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(mock_fsm, trade_id="99001")

        closed_writes = [
            w for w in written
            if isinstance(w, dict) and w.get("event_type") == "POSITION_CLOSED"
        ]
        assert len(closed_writes) == 1, (
            f"Expected one POSITION_CLOSED write, got {len(closed_writes)}"
        )
        w = closed_writes[0]
        assert "trade_id" in w, (
            "POSITION_CLOSED must have top-level 'trade_id' field (HB-2 Phase 2)"
        )

    def test_position_closed_trade_id_equals_cached_value(self):
        """
        POSITION_CLOSED top-level trade_id must equal the cached tradeId value.
        FAILS before Phase 2 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(mock_fsm, trade_id="99001")

        closed_writes = [
            w for w in written
            if isinstance(w, dict) and w.get("event_type") == "POSITION_CLOSED"
        ]
        if not closed_writes:
            pytest.skip("POSITION_CLOSED not written")
        w = closed_writes[0]
        if "trade_id" not in w:
            pytest.fail(
                "trade_id not present in POSITION_CLOSED (pre-implementation)")
        assert w["trade_id"] == "99001"

    def test_position_closed_side_is_not_na(self):
        """
        POSITION_CLOSED 'side' must be a real entry direction (BUY or SELL), not 'N/A'.
        FAILS before Phase 2 implementation (currently hardcoded 'N/A').
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(mock_fsm, entry_side="BUY")

        closed_writes = [
            w for w in written
            if isinstance(w, dict) and w.get("event_type") == "POSITION_CLOSED"
        ]
        if not closed_writes:
            pytest.skip("POSITION_CLOSED not written")
        w = closed_writes[0]
        assert w.get("side") in ("BUY", "SELL"), (
            f"POSITION_CLOSED side must be BUY or SELL, got {w.get('side')!r}"
        )

    def test_position_closed_side_equals_cached_entry_side(self):
        """
        POSITION_CLOSED side must match the pre-cached entry side exactly.
        FAILS before Phase 2 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(mock_fsm, entry_side="BUY")

        closed_writes = [
            w for w in written
            if isinstance(w, dict) and w.get("event_type") == "POSITION_CLOSED"
        ]
        if not closed_writes:
            pytest.skip("POSITION_CLOSED not written")
        w = closed_writes[0]
        assert w.get("side") == "BUY", f"Expected 'BUY', got {w.get('side')!r}"

    def test_position_closed_side_fallback_to_na_when_cache_empty(self):
        """
        Fail-closed: when _last_entry_side_by_symbol has no entry for the symbol,
        POSITION_CLOSED side must fall back to 'N/A' (graceful, not crash or absent key).
        """
        import apps.reference.domains.execution_position.event_handlers as handlers_mod

        mock_fsm = _make_mock_fsm()
        mock_fsm._last_entry_side_by_symbol = {}   # empty
        mock_fsm._last_trade_id_by_symbol = {}      # empty
        mock_fsm._last_lifecycle_ikey_by_symbol = {}
        mock_fsm._prev_position_amts = {"BTCUSDT": 1.0}
        mock_fsm._last_lifecycle_rid_by_symbol = {"BTCUSDT": ""}
        mock_fsm._last_lifecycle_fill_price_by_symbol = {}
        mock_fsm._last_realized_pnl_by_symbol = {}

        event = SimpleNamespace(
            pld={"positions": [{"symbol": "BTCUSDT", "positionAmt": 0.0}]}
        )
        written = []
        with patch.object(handlers_mod, "_trade_lifecycle", None), \
                patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
                patch("apps.reference.domains.execution_position.event_handlers.get_clock") as mock_clock:
            mock_clock.return_value.now_sec.return_value = 1_700_000.0
            mock_clock.return_value.now_ms.return_value = 1_700_000_000_000
            mock_log_fn.return_value.write.side_effect = written.append
            handler = handlers_mod.EPEventHandlers(mock_fsm)
            handler.on_portfolio_state_updated(event)

        closed = [
            w for w in written
            if isinstance(w, dict) and w.get("event_type") == "POSITION_CLOSED"
        ]
        if not closed:
            pytest.skip("POSITION_CLOSED not written in empty-cache scenario")
        w = closed[0]
        assert w.get("side") == "N/A", (
            f"Fallback side must be 'N/A' when cache empty, got {w.get('side')!r}"
        )

    def test_trade_id_and_side_cleared_after_position_closed(self):
        """
        _last_trade_id_by_symbol and _last_entry_side_by_symbol must be popped
        after POSITION_CLOSED write to prevent stale values leaking into next lifecycle.
        FAILS before Phase 2 implementation (cleanup block not yet added).
        """
        mock_fsm = _make_mock_fsm()
        mock_fsm._last_trade_id_by_symbol = {"BTCUSDT": "99001"}
        mock_fsm._last_entry_side_by_symbol = {"BTCUSDT": "BUY"}

        _run_portfolio_close(mock_fsm, trade_id="99001", entry_side="BUY")

        assert "BTCUSDT" not in mock_fsm._last_trade_id_by_symbol, (
            "_last_trade_id_by_symbol[BTCUSDT] must be popped after POSITION_CLOSED write"
        )
        assert "BTCUSDT" not in mock_fsm._last_entry_side_by_symbol, (
            "_last_entry_side_by_symbol[BTCUSDT] must be popped after POSITION_CLOSED write"
        )
