from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class _CaptureBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, str | None, object, dict]] = []

    def emit(self, topic: str, payload=None, why=None, data_ref=None, **kwargs) -> None:
        self.events.append((topic, payload or {}, why, data_ref, kwargs))


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
    mock_fsm._close_accounting_truth_by_symbol = {}
    mock_fsm._pending_intent_data = {}
    mock_fsm._pending_entry_meta = {}
    mock_fsm._pending_brackets = {}
    mock_fsm._open_regime_by_symbol = {}
    mock_fsm._open_strategy_by_symbol = {}
    mock_fsm._bracket_owner_by_symbol = {}
    mock_fsm._last_position_closed_ts = {}
    mock_fsm._mark_processed_event.return_value = True
    mock_fsm.exposure_guard.state.postfill_reservations = {}
    mock_fsm.exposure_guard.expire_stale.return_value = []
    mock_fsm.exposure_guard.get_exposure_summary.return_value = {}
    mock_fsm._get_async_loop.return_value = None
    mock_fsm._latest_portfolio_state = {}
    mock_fsm.bus = _CaptureBus()
    mock_fsm.get_recent_terminal_close_proof.return_value = None
    return mock_fsm


def test_terminal_close_emits_evt_position_closed_with_required_fields() -> None:
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod

    fsm = _make_mock_fsm()
    fsm._prev_position_amts = {"BTCUSDT": 1.0}
    fsm._last_lifecycle_rid_by_symbol = {"BTCUSDT": "ENTRY-BTCUSDT-abc456"}
    fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 50100.0}
    fsm._last_realized_pnl_by_symbol = {"BTCUSDT": -1.0}
    fsm._last_lifecycle_ikey_by_symbol = {"BTCUSDT": "idem-key-001"}
    fsm._last_trade_id_by_symbol = {"BTCUSDT": "10001"}
    fsm._last_entry_side_by_symbol = {"BTCUSDT": "BUY"}
    fsm._accumulated_fees_by_symbol = {"BTCUSDT": 0.09}
    fsm._close_accounting_truth_by_symbol = {
        "BTCUSDT": {
            "trade_id": "10001",
            "close_price": 50100.0,
            "realized_pnl": -1.0,
            "fees": 0.09,
            "lifecycle_id": "idem-key-001",
            "entry_side": "BUY",
            "close_reason": "POSITION_CLOSED_DETECTED",
            "pnl_status": "resolved",
            "pnl_source": "close_fill",
            "economic_close_detected": True,
            "economic_close_kind": "explicit_close_fill",
        }
    }
    fsm._open_regime_by_symbol = {
        "BTCUSDT": {
            "regime_epoch_ref": "stable_epoch:BTCUSDT:1700000000000",
            "regime": "TREND_UP",
        }
    }

    event = SimpleNamespace(pld={"positions": [{"symbol": "BTCUSDT", "positionAmt": 0.0}]})

    with patch.object(handlers_mod, "_trade_lifecycle", None), \
            patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
            patch("apps.reference.domains.execution_position.orchestration.event_handlers.get_clock") as mock_clock:
        mock_clock.return_value.now_sec.return_value = 1_700_000.0
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_000
        mock_log_fn.return_value.write.side_effect = lambda *_args, **_kwargs: None

        handler = handlers_mod.EPEventHandlers(fsm)
        handler.on_portfolio_state_updated(event)

    emitted = [payload for topic, payload, _why, _data_ref, _kwargs in fsm.bus.events if topic == "EVT:POSITION_CLOSED"]
    assert len(emitted) == 1
    payload = emitted[0]
    assert payload["symbol"] == "BTCUSDT"
    assert payload["trade_id"] == "10001"
    assert payload["close_reason"] == "POSITION_CLOSED_DETECTED"
    assert payload["close_ts_ms"] == 1_700_000_000
    assert payload["fees"] == 0.09
    assert payload["realized_pnl_net"] == -1.09
    assert payload["entry_regime_epoch_ref"] == "stable_epoch:BTCUSDT:1700000000000"


def test_terminal_close_emits_explicit_null_entry_epoch_when_unavailable() -> None:
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod

    fsm = _make_mock_fsm()
    fsm._prev_position_amts = {"BTCUSDT": 1.0}
    fsm._last_lifecycle_rid_by_symbol = {"BTCUSDT": "ENTRY-BTCUSDT-abc456"}
    fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 50100.0}
    fsm._last_realized_pnl_by_symbol = {"BTCUSDT": -1.0}
    fsm._last_lifecycle_ikey_by_symbol = {"BTCUSDT": "idem-key-001"}
    fsm._last_trade_id_by_symbol = {"BTCUSDT": "10001"}
    fsm._last_entry_side_by_symbol = {"BTCUSDT": "BUY"}
    fsm._accumulated_fees_by_symbol = {"BTCUSDT": 0.09}
    fsm._close_accounting_truth_by_symbol = {
        "BTCUSDT": {
            "trade_id": "10001",
            "close_price": 50100.0,
            "realized_pnl": -1.0,
            "fees": 0.09,
            "lifecycle_id": "idem-key-001",
            "entry_side": "BUY",
            "close_reason": "POSITION_CLOSED_DETECTED",
            "pnl_status": "resolved",
            "pnl_source": "close_fill",
            "economic_close_detected": True,
            "economic_close_kind": "explicit_close_fill",
        }
    }
    fsm._open_regime_by_symbol = {"BTCUSDT": {"regime": "TREND_UP"}}

    event = SimpleNamespace(pld={"positions": [{"symbol": "BTCUSDT", "positionAmt": 0.0}]})

    with patch.object(handlers_mod, "_trade_lifecycle", None), \
            patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
            patch("apps.reference.domains.execution_position.orchestration.event_handlers.get_clock") as mock_clock:
        mock_clock.return_value.now_sec.return_value = 1_700_000.0
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_000
        mock_log_fn.return_value.write.side_effect = lambda *_args, **_kwargs: None

        handler = handlers_mod.EPEventHandlers(fsm)
        handler.on_portfolio_state_updated(event)

    emitted = [payload for topic, payload, _why, _data_ref, _kwargs in fsm.bus.events if topic == "EVT:POSITION_CLOSED"]
    assert len(emitted) == 1
    assert "entry_regime_epoch_ref" in emitted[0]
    assert emitted[0]["entry_regime_epoch_ref"] is None
