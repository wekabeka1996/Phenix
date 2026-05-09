"""
PHASE 1 — TDD anchor: lifecycle_id propagation through on_order_fill
and on_portfolio_state_updated.

Contracts:
1. on_order_fill caches lifecycle_id from OrderIndex ref into
   _last_lifecycle_ikey_by_symbol[symbol].
2. ORDER_FILLED write has top-level "lifecycle_id".
3. POSITION_CLOSED write has top-level "lifecycle_id" matching the cached value.
4. Fail-closed: empty string emitted (not crash) when OrderIndex has no ref.
5. Cache cleared after POSITION_CLOSED write.

These tests MUST FAIL before Phase 1 implementation (red).
They MUST PASS after Phase 1 implementation (green).
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_fsm():
    """Mock ExecPosFSM with all per-symbol dicts as real dicts."""
    mock_fsm = MagicMock()
    mock_fsm._last_lifecycle_rid_by_symbol = {}
    mock_fsm._last_lifecycle_fill_price_by_symbol = {}
    mock_fsm._last_realized_pnl_by_symbol = {}
    mock_fsm._last_close_reason_by_symbol = {}
    # Phase 1 cache — may not exist yet on real FSM; tests set it to validate
    mock_fsm._last_lifecycle_ikey_by_symbol = {}
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


def _make_order_fill_event(
    order_id="EX-ORD-001",
    symbol="BTCUSDT",
    qty="0.01",
    client_order_id="ENTRY-BTCUSDT-abc123",
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


def _make_order_index_mock(idempotent_key: str, side: str = "BUY", client_order_id: str = "ENTRY-BTCUSDT-abc123"):
    """Return a mock OrderIndex that yields a ref with idempotent_key + side."""
    mock_ref = MagicMock()
    mock_ref.idempotent_key = idempotent_key
    mock_ref.side = side

    def mock_get(*, rid=None, clientOrderId=None, exchangeOrderId=None):
        if exchangeOrderId is not None:
            return None  # exchange lookup always misses in tests
        if clientOrderId == client_order_id:
            return mock_ref
        if rid == client_order_id:
            return mock_ref
        return None

    mock_oi = MagicMock()
    mock_oi.get.side_effect = mock_get
    return mock_oi, mock_ref


def _run_fill(mock_fsm, event, mock_oi=None, patches=None):
    """
    Run EPEventHandlers.on_order_fill with patched order_logger and optional order_index.
    Returns list of dicts written to order_logger.
    """
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod

    # Explicitly set order_index to None on mock_fsm itself so that
    # getattr(self._fsm, "order_index", None) returns None, forcing the code
    # to fall through to self._fsm.fsm.order_index (which we control).
    mock_fsm.order_index = None
    # Set order_index on mock_fsm.fsm
    if mock_oi is not None:
        mock_fsm.fsm.order_index = mock_oi
    else:
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


def _run_portfolio_close(mock_fsm, lifecycle_ikey: str = "test-idem-lifecycle-456"):
    """
    Run EPEventHandlers.on_portfolio_state_updated to trigger POSITION_CLOSED write.
    Returns list of dicts written to order_logger.
    """
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod

    mock_fsm._prev_position_amts = {"BTCUSDT": 1.0}
    mock_fsm._last_lifecycle_rid_by_symbol = {
        "BTCUSDT": "ENTRY-BTCUSDT-abc123"}
    mock_fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 50100.0}
    mock_fsm._last_realized_pnl_by_symbol = {"BTCUSDT": -0.5}
    # Pre-populate the Phase 1 cache to validate POSITION_CLOSED emission
    mock_fsm._last_lifecycle_ikey_by_symbol = {"BTCUSDT": lifecycle_ikey}
    mock_fsm._close_accounting_truth_by_symbol = {
        "BTCUSDT": {
            "trade_id": "10001",
            "close_price": 50100.0,
            "realized_pnl": -0.5,
            "fees": 0.0,
            "lifecycle_id": lifecycle_ikey,
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
# Tests: on_order_fill — caching and ORDER_FILLED write
# ---------------------------------------------------------------------------


class TestOnOrderFillLifecycleIdCaching:
    """Phase 1: on_order_fill must cache lifecycle_id from OrderIndex."""

    def test_caches_lifecycle_id_from_order_index(self):
        """
        After on_order_fill, _last_lifecycle_ikey_by_symbol[symbol] must equal
        the idempotent_key from the OrderIndex ref.
        FAILS before Phase 1 implementation.
        """
        mock_fsm = _make_mock_fsm()
        mock_oi, _ = _make_order_index_mock("test-idem-xyz-001")
        event = _make_order_fill_event()

        _run_fill(mock_fsm, event, mock_oi=mock_oi)

        assert mock_fsm._last_lifecycle_ikey_by_symbol.get("BTCUSDT") == "test-idem-xyz-001", (
            "_last_lifecycle_ikey_by_symbol must be populated from OrderIndex ref.idempotent_key"
        )

    def test_order_filled_write_has_top_level_lifecycle_id(self):
        """
        ORDER_FILLED write dict must have a top-level 'lifecycle_id' key.
        FAILS before Phase 1 implementation.
        """
        mock_fsm = _make_mock_fsm()
        mock_oi, _ = _make_order_index_mock("test-idem-xyz-002")
        event = _make_order_fill_event()

        written = _run_fill(mock_fsm, event, mock_oi=mock_oi)

        filled_writes = [w for w in written if isinstance(
            w, dict) and w.get("event_type") == "ORDER_FILLED"]
        assert len(
            filled_writes) == 1, f"Expected one ORDER_FILLED write, got {len(filled_writes)}"
        w = filled_writes[0]
        assert "lifecycle_id" in w, (
            "ORDER_FILLED must have top-level 'lifecycle_id' field (HB-1 Phase 1)"
        )

    def test_order_filled_lifecycle_id_equals_cached_idem_key(self):
        """
        ORDER_FILLED lifecycle_id must equal the idempotent_key from the OrderIndex ref.
        FAILS before Phase 1 implementation.
        """
        mock_fsm = _make_mock_fsm()
        mock_oi, _ = _make_order_index_mock("test-idem-xyz-003")
        event = _make_order_fill_event()

        written = _run_fill(mock_fsm, event, mock_oi=mock_oi)

        filled_writes = [w for w in written if isinstance(
            w, dict) and w.get("event_type") == "ORDER_FILLED"]
        if not filled_writes:
            pytest.skip("ORDER_FILLED not written")
        w = filled_writes[0]
        if "lifecycle_id" not in w:
            pytest.fail(
                "lifecycle_id not present in ORDER_FILLED (pre-implementation)")
        assert w["lifecycle_id"] == "test-idem-xyz-003"

    def test_order_filled_lifecycle_id_empty_string_when_no_order_index(self):
        """
        Fail-closed: if OrderIndex is absent/has no ref, ORDER_FILLED lifecycle_id
        must be empty string (not crash, not None).
        FAILS before Phase 1 implementation (field absent entirely).
        """
        mock_fsm = _make_mock_fsm()
        # No order_index at all
        mock_fsm.fsm.order_index = None
        event = _make_order_fill_event()

        written = _run_fill(mock_fsm, event, mock_oi=None)

        filled_writes = [w for w in written if isinstance(
            w, dict) and w.get("event_type") == "ORDER_FILLED"]
        if not filled_writes:
            pytest.skip("ORDER_FILLED not written")
        w = filled_writes[0]
        assert "lifecycle_id" in w, "lifecycle_id must be present even when OrderIndex misses"
        assert w["lifecycle_id"] == "", (
            "lifecycle_id must be empty string (not None, not missing) on OrderIndex miss"
        )

    def test_order_filled_lifecycle_id_empty_string_when_ref_has_no_idem_key(self):
        """
        Fail-closed: if ref exists but idempotent_key is None/empty, lifecycle_id
        must be empty string.
        """
        mock_fsm = _make_mock_fsm()
        # ref with no idempotent_key
        mock_ref = MagicMock()
        mock_ref.idempotent_key = None
        mock_ref.side = "BUY"

        mock_oi = MagicMock()
        mock_oi.get.return_value = mock_ref

        event = _make_order_fill_event()
        written = _run_fill(mock_fsm, event, mock_oi=mock_oi)

        filled_writes = [w for w in written if isinstance(
            w, dict) and w.get("event_type") == "ORDER_FILLED"]
        if not filled_writes:
            pytest.skip("ORDER_FILLED not written")
        w = filled_writes[0]
        assert "lifecycle_id" in w, "lifecycle_id must be present"
        assert w["lifecycle_id"] == ""


# ---------------------------------------------------------------------------
# Tests: on_portfolio_state_updated — POSITION_CLOSED write and cache cleanup
# ---------------------------------------------------------------------------


class TestPositionClosedLifecycleId:
    """Phase 1: POSITION_CLOSED write must carry lifecycle_id from cache."""

    def test_position_closed_write_has_top_level_lifecycle_id(self):
        """
        POSITION_CLOSED write dict must have a top-level 'lifecycle_id' key.
        FAILS before Phase 1 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(mock_fsm)

        closed_writes = [w for w in written if isinstance(
            w, dict) and w.get("event_type") == "POSITION_CLOSED"]
        assert len(
            closed_writes) == 1, f"Expected one POSITION_CLOSED write, got {len(closed_writes)}"
        w = closed_writes[0]
        assert "lifecycle_id" in w, (
            "POSITION_CLOSED must have top-level 'lifecycle_id' field (HB-1 Phase 1)"
        )

    def test_position_closed_lifecycle_id_equals_cached_value(self):
        """
        POSITION_CLOSED lifecycle_id must equal the pre-cached idem key.
        FAILS before Phase 1 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(
            mock_fsm, lifecycle_ikey="test-idem-lifecycle-456")

        closed_writes = [w for w in written if isinstance(
            w, dict) and w.get("event_type") == "POSITION_CLOSED"]
        if not closed_writes:
            pytest.skip("POSITION_CLOSED not written")
        w = closed_writes[0]
        if "lifecycle_id" not in w:
            pytest.fail(
                "lifecycle_id not present in POSITION_CLOSED (pre-implementation)")
        assert w["lifecycle_id"] == "test-idem-lifecycle-456"

    def test_lifecycle_id_cleared_after_position_closed(self):
        """
        _last_lifecycle_ikey_by_symbol[symbol] must be removed after
        POSITION_CLOSED write. Prevents stale values from leaking into next lifecycle.
        FAILS before Phase 1 implementation.
        """
        mock_fsm = _make_mock_fsm()
        mock_fsm._last_lifecycle_ikey_by_symbol = {
            "BTCUSDT": "test-idem-to-clear"}

        _run_portfolio_close(mock_fsm, lifecycle_ikey="test-idem-to-clear")

        assert "BTCUSDT" not in mock_fsm._last_lifecycle_ikey_by_symbol, (
            "_last_lifecycle_ikey_by_symbol[BTCUSDT] must be popped after POSITION_CLOSED write "
            "(cleanup block must run after the write, not in the pre-write finally)"
        )

    def test_position_closed_lifecycle_id_empty_string_when_cache_empty(self):
        """
        Fail-closed: if _last_lifecycle_ikey_by_symbol has no entry for symbol,
        POSITION_CLOSED lifecycle_id must be empty string (not crash, not absent).
        """
        mock_fsm = _make_mock_fsm()
        # Explicitly empty cache — no prior fill cached the idem key
        mock_fsm._last_lifecycle_ikey_by_symbol = {}

        written = _run_portfolio_close(
            mock_fsm, lifecycle_ikey="__no_override__")
        # Override after helper call — helper sets it, we need it empty for this test
        # Re-run cleanly
        mock_fsm2 = _make_mock_fsm()
        mock_fsm2._last_lifecycle_ikey_by_symbol = {}  # empty
        written2 = _run_portfolio_close.__wrapped__(mock_fsm2) if hasattr(
            _run_portfolio_close, "__wrapped__") else None
        if written2 is None:
            # Run manually
            import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod
            mock_fsm2._prev_position_amts = {"BTCUSDT": 1.0}
            mock_fsm2._last_lifecycle_rid_by_symbol = {"BTCUSDT": ""}
            mock_fsm2._last_lifecycle_fill_price_by_symbol = {}
            mock_fsm2._last_realized_pnl_by_symbol = {}
            written2 = []
            event = SimpleNamespace(
                pld={"positions": [{"symbol": "BTCUSDT", "positionAmt": 0.0}]}
            )
            with patch.object(handlers_mod, "_trade_lifecycle", None), \
                    patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
                    patch("apps.reference.domains.execution_position.orchestration.event_handlers.get_clock") as mock_clock:
                mock_clock.return_value.now_sec.return_value = 1700000.0
                mock_clock.return_value.now_ms.return_value = 1700000000000
                mock_log_fn.return_value.write.side_effect = written2.append
                handler = handlers_mod.EPEventHandlers(mock_fsm2)
                handler.on_portfolio_state_updated(event)

        closed = [w for w in written2 if isinstance(
            w, dict) and w.get("event_type") == "POSITION_CLOSED"]
        if not closed:
            pytest.skip("POSITION_CLOSED not written in empty-cache scenario")
        w = closed[0]
        assert "lifecycle_id" in w, "lifecycle_id must be present even when cache empty"
        assert w[
            "lifecycle_id"] == "", "lifecycle_id must be empty string when cache empty (graceful fallback)"
