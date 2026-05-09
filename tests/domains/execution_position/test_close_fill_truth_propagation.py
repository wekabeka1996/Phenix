from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


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
    mock_fsm._last_position_closed_ts = {}
    mock_fsm._prev_position_amts = {}
    mock_fsm._mark_processed_event.return_value = True
    mock_fsm.exposure_guard.state.postfill_reservations = {}
    mock_fsm.exposure_guard.expire_stale.return_value = []
    mock_fsm.exposure_guard.get_exposure_summary.return_value = {}
    mock_fsm._get_async_loop.return_value = None
    mock_fsm._latest_portfolio_state = {}
    mock_fsm.bus = _CaptureBus()
    mock_fsm.get_recent_terminal_close_proof.return_value = None
    mock_fsm.order_index = None
    mock_fsm.fsm.order_index = None
    return mock_fsm


def _make_fill_event(
    *,
    symbol: str = "BTCUSDT",
    client_order_id: str,
    order_id: str,
    trade_id: str,
    side: str,
    price: str,
    realized_pnl: str,
    commission: str,
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
            "realizedPnl": realized_pnl,
            "price": price,
            "side": side,
        },
        rid=client_order_id,
    )


def _portfolio_close_event(symbol: str = "BTCUSDT"):
    return SimpleNamespace(pld={"positions": [{"symbol": symbol, "positionAmt": 0.0}]})


def _run_fill(fsm, event):
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod

    written = []
    with patch.object(handlers_mod, "_trade_lifecycle", None), \
            patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
            patch("apps.reference.domains.execution_position.orchestration.event_handlers.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_100
        mock_log_fn.return_value.write.side_effect = written.append
        handlers_mod.EPEventHandlers(fsm).on_order_fill(event)
    return written


def _run_portfolio_close(fsm):
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod

    written = []
    with patch.object(handlers_mod, "_trade_lifecycle", None), \
            patch.object(handlers_mod, "_get_order_logger") as mock_log_fn, \
            patch("apps.reference.domains.execution_position.orchestration.event_handlers.get_clock") as mock_clock:
        mock_clock.return_value.now_sec.return_value = 1_700_000.0
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_000
        mock_log_fn.return_value.write.side_effect = written.append
        handlers_mod.EPEventHandlers(fsm).on_portfolio_state_updated(
            _portfolio_close_event()
        )
    return written


def _position_closed_payload(fsm):
    payloads = [
        payload
        for topic, payload, _why, _data_ref, _kwargs in fsm.bus.events
        if topic == "EVT:POSITION_CLOSED"
    ]
    assert len(payloads) == 1
    return payloads[0]


def test_sidecar_close_truth_uses_close_fill_not_stale_entry_cache() -> None:
    fsm = _make_mock_fsm()
    fsm._prev_position_amts = {"BTCUSDT": 0.01}
    fsm._last_lifecycle_rid_by_symbol = {"BTCUSDT": "ENTRY-BTCUSDT-open-1"}
    fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 81000.0}
    fsm._last_lifecycle_ikey_by_symbol = {"BTCUSDT": "life-1"}
    fsm._last_trade_id_by_symbol = {"BTCUSDT": "entry-trade-stale"}
    fsm._last_entry_side_by_symbol = {"BTCUSDT": "BUY"}
    fsm._open_regime_by_symbol = {"BTCUSDT": {"regime_epoch_ref": "stable_epoch:BTCUSDT:1"}}

    _run_fill(
        fsm,
        _make_fill_event(
            client_order_id="CLOSE-BTCUSDT-close-1",
            order_id="close-order-1",
            trade_id="close-trade-1",
            side="SELL",
            price="80450.0",
            realized_pnl="-12.5",
            commission="0.4",
        ),
    )
    written = _run_portfolio_close(fsm)
    payload = _position_closed_payload(fsm)

    assert payload["pnl_status"] == "resolved"
    assert payload["trade_id"] == "close-trade-1"
    assert payload["close_price"] == pytest.approx(80450.0)
    assert payload["realized_pnl"] == pytest.approx(-12.5)
    assert payload["realized_pnl_net"] == pytest.approx(-12.9)
    assert payload["trade_id"] != "entry-trade-stale"
    assert payload["close_reason"] == "CLOSE"
    assert payload["economic_close_kind"] == "explicit_close_fill"

    close_write = next(
        item for item in written if isinstance(item, dict) and item.get("event_type") == "POSITION_CLOSED"
    )
    assert close_write["metadata"]["close_price"] == pytest.approx(80450.0)


def test_sidecar_close_without_fill_truth_emits_unresolved_not_fake_profit() -> None:
    fsm = _make_mock_fsm()
    fsm._prev_position_amts = {"BTCUSDT": 0.01}
    fsm._last_lifecycle_rid_by_symbol = {"BTCUSDT": "ENTRY-BTCUSDT-open-1"}
    fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 81000.0}
    fsm._last_realized_pnl_by_symbol = {"BTCUSDT": 14.0}
    fsm._last_lifecycle_ikey_by_symbol = {"BTCUSDT": "life-1"}
    fsm._last_trade_id_by_symbol = {"BTCUSDT": "entry-trade-stale"}
    fsm._last_entry_side_by_symbol = {"BTCUSDT": "BUY"}
    fsm._accumulated_fees_by_symbol = {"BTCUSDT": 0.2}
    fsm._open_regime_by_symbol = {"BTCUSDT": {"regime_epoch_ref": "stable_epoch:BTCUSDT:1"}}

    _run_portfolio_close(fsm)
    payload = _position_closed_payload(fsm)

    assert payload["pnl_status"] == "unresolved"
    assert payload["pnl_source"] == "unresolved"
    assert payload["realized_pnl"] is None
    assert payload["realized_pnl_net"] is None
    assert payload["fees"] is None
    assert payload["trade_id"] is None
    assert payload["accounting_unresolved_reason"] == "missing_close_fill_truth"


def test_opposite_entry_fill_is_accounted_as_entry_netting_close() -> None:
    fsm = _make_mock_fsm()
    fsm._prev_position_amts = {"BTCUSDT": 0.055}
    fsm._last_lifecycle_rid_by_symbol = {"BTCUSDT": "ENTRY-BTCUSDT-open-1"}
    fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 81434.8}
    fsm._last_lifecycle_ikey_by_symbol = {"BTCUSDT": "life-btc-1"}
    fsm._last_entry_side_by_symbol = {"BTCUSDT": "BUY"}
    fsm._open_regime_by_symbol = {"BTCUSDT": {"regime_epoch_ref": "stable_epoch:BTCUSDT:1"}}

    _run_fill(
        fsm,
        _make_fill_event(
            client_order_id="ENTRY-BTCUSDT-sell-net",
            order_id="btc-entry-sell-1",
            trade_id="btc-close-trade-1",
            side="SELL",
            price="81052.3",
            realized_pnl="-21.0375",
            commission="0.8925",
        ),
    )
    _run_portfolio_close(fsm)
    payload = _position_closed_payload(fsm)

    assert payload["pnl_status"] == "resolved"
    assert payload["close_reason"] == "ENTRY_NETTING_CLOSE"
    assert payload["economic_close_detected"] is True
    assert payload["economic_close_kind"] == "entry_netting_close"
    assert payload["trade_id"] == "btc-close-trade-1"
    assert payload["realized_pnl"] == pytest.approx(-21.0375)
    assert payload["realized_pnl_net"] == pytest.approx(-21.93)
