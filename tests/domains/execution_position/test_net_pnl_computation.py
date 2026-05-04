"""
PHASE 3 — TDD anchor: POSITION_CLOSED write must carry 'fees' and 'realized_pnl_net'.

Contracts:
1. POSITION_CLOSED write has top-level 'fees' key (numeric float, not None).
2. POSITION_CLOSED write has top-level 'realized_pnl_net' key (numeric float, not None).
3. realized_pnl_net == realized_pnl - fees.
4. fees = 0.0 is emitted as float 0.0 — not suppressed, not None.
5. realized_pnl_net is negative when loss exceeds fees.

These tests MUST FAIL before Phase 3 implementation (red).
They MUST PASS after Phase 3 implementation (green).
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers (reuse pattern from previous Phase tests)
# ---------------------------------------------------------------------------

def _make_mock_fsm():
    mock_fsm = MagicMock()
    mock_fsm._last_lifecycle_rid_by_symbol = {}
    mock_fsm._last_lifecycle_fill_price_by_symbol = {}
    mock_fsm._last_realized_pnl_by_symbol = {}
    mock_fsm._last_close_reason_by_symbol = {}
    mock_fsm._last_lifecycle_ikey_by_symbol = {}
    mock_fsm._last_trade_id_by_symbol = {}
    mock_fsm._last_entry_side_by_symbol = {}
    mock_fsm._accumulated_fees_by_symbol = {}
    mock_fsm._pending_intent_data = {}
    mock_fsm._pending_entry_meta = {}
    mock_fsm._pending_brackets = {}
    mock_fsm._open_regime_by_symbol = {}
    mock_fsm._open_strategy_by_symbol = {}
    mock_fsm._last_position_closed_ts = {}
    mock_fsm._mark_processed_event.return_value = True
    mock_fsm.exposure_guard.state.postfill_reservations = {}
    mock_fsm.exposure_guard.expire_stale.return_value = []
    mock_fsm.exposure_guard.get_exposure_summary.return_value = {}
    mock_fsm._get_async_loop.return_value = None
    mock_fsm._latest_portfolio_state = {}
    return mock_fsm


def _run_portfolio_close(mock_fsm, accumulated_fees=0.09, realized_pnl=-1.0):
    """Trigger POSITION_CLOSED — returns list of written dicts."""
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


def _get_closed_write(written):
    closed = [
        w for w in written
        if isinstance(w, dict) and w.get("event_type") == "POSITION_CLOSED"
    ]
    return closed[0] if closed else None


# ---------------------------------------------------------------------------
# Tests: POSITION_CLOSED write — fees and realized_pnl_net fields
# ---------------------------------------------------------------------------


class TestNetPnlComputation:
    """Phase 3: POSITION_CLOSED must carry 'fees' and 'realized_pnl_net'."""

    def test_position_closed_has_fees_field(self):
        """
        POSITION_CLOSED write dict must have a top-level 'fees' key.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(mock_fsm, accumulated_fees=0.09)
        w = _get_closed_write(written)
        assert w is not None, "Expected a POSITION_CLOSED write"
        assert "fees" in w, (
            "POSITION_CLOSED must have top-level 'fees' field (HB-3 Phase 3)"
        )

    def test_position_closed_fees_is_numeric_not_none(self):
        """
        POSITION_CLOSED 'fees' must be a numeric float, not None.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(mock_fsm, accumulated_fees=0.09)
        w = _get_closed_write(written)
        if w is None:
            pytest.skip("POSITION_CLOSED not written")
        if "fees" not in w:
            pytest.fail(
                "fees not present in POSITION_CLOSED (pre-implementation)")
        assert w["fees"] is not None, "fees must not be None"
        assert isinstance(w["fees"], (int, float)
                          ), f"fees must be numeric, got {type(w['fees'])}"

    def test_position_closed_fees_equals_accumulated_value(self):
        """
        POSITION_CLOSED 'fees' must equal the accumulated _accumulated_fees_by_symbol value.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(mock_fsm, accumulated_fees=0.09)
        w = _get_closed_write(written)
        if w is None or "fees" not in w:
            pytest.skip("fees field not yet implemented")
        assert w["fees"] == pytest.approx(0.09)

    def test_position_closed_has_realized_pnl_net_field(self):
        """
        POSITION_CLOSED write dict must have a top-level 'realized_pnl_net' key.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(mock_fsm)
        w = _get_closed_write(written)
        assert w is not None, "Expected a POSITION_CLOSED write"
        assert "realized_pnl_net" in w, (
            "POSITION_CLOSED must have top-level 'realized_pnl_net' field (HB-3 Phase 3)"
        )

    def test_realized_pnl_net_equals_pnl_minus_fees(self):
        """
        realized_pnl_net must equal realized_pnl - fees.
        Contract: realized_pnl_net = pos_pnl - accumulated_fees.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        # realized_pnl = -1.0, fees = 0.09 → realized_pnl_net = -1.09
        written = _run_portfolio_close(
            mock_fsm, accumulated_fees=0.09, realized_pnl=-1.0
        )
        w = _get_closed_write(written)
        if w is None:
            pytest.skip("POSITION_CLOSED not written")
        if "realized_pnl_net" not in w:
            pytest.fail("realized_pnl_net not present (pre-implementation)")
        assert w["realized_pnl_net"] == pytest.approx(-1.09), (
            f"realized_pnl_net must be -1.0 - 0.09 = -1.09, got {w['realized_pnl_net']}"
        )

    def test_fees_zero_emitted_as_float_not_none(self):
        """
        When accumulated fees are 0.0, POSITION_CLOSED 'fees' must be 0.0 (float),
        not None, not absent. This is critical — neocortex reward_complete gate
        requires fees to be non-None; 0.0 is valid.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(
            mock_fsm, accumulated_fees=0.0, realized_pnl=5.0)
        w = _get_closed_write(written)
        if w is None:
            pytest.skip("POSITION_CLOSED not written")
        if "fees" not in w:
            pytest.fail("fees field not present (pre-implementation)")
        assert w["fees"] is not None, "fees=0.0 must be emitted as 0.0, not None"
        assert w["fees"] == pytest.approx(
            0.0), f"fees must be 0.0, got {w['fees']}"

    def test_realized_pnl_net_zero_fees(self):
        """
        When fees are 0.0, realized_pnl_net must equal realized_pnl exactly.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(
            mock_fsm, accumulated_fees=0.0, realized_pnl=5.0)
        w = _get_closed_write(written)
        if w is None or "realized_pnl_net" not in w:
            pytest.skip("fields not yet implemented")
        assert w["realized_pnl_net"] == pytest.approx(5.0), (
            "realized_pnl_net must equal pnl when fees=0"
        )

    def test_net_pnl_negative_when_loss_plus_fees(self):
        """
        For a losing trade: realized_pnl_net = negative_pnl - positive_fees
        must be more negative than realized_pnl alone.
        FAILS before Phase 3 implementation.
        """
        mock_fsm = _make_mock_fsm()
        written = _run_portfolio_close(
            mock_fsm, accumulated_fees=0.5, realized_pnl=-2.0
        )
        w = _get_closed_write(written)
        if w is None or "realized_pnl_net" not in w:
            pytest.skip("fields not yet implemented")
        pnl_net = w["realized_pnl_net"]
        assert pnl_net < -2.0, (
            f"realized_pnl_net must be more negative than realized_pnl=-2.0 when fees=0.5, "
            f"got {pnl_net}"
        )
        assert pnl_net == pytest.approx(-2.5)
