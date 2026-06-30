from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class _CaptureBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, str | None, object, dict]] = []

    def emit(self, topic: str, payload=None, why=None, data_ref=None, **kwargs) -> None:
        self.events.append((topic, payload or {}, why, data_ref, kwargs))


def _make_mock_fsm(symbol: str, *, position_amt: str, strategy_id: str = "mean_reversion"):
    fsm = MagicMock()
    fsm._last_lifecycle_rid_by_symbol = {symbol: f"ENTRY-{symbol}-local"}
    fsm._last_lifecycle_fill_price_by_symbol = {}
    fsm._last_realized_pnl_by_symbol = {}
    fsm._last_close_reason_by_symbol = {}
    fsm._last_lifecycle_ikey_by_symbol = {symbol: f"life-{symbol}"}
    fsm._last_trade_id_by_symbol = {}
    fsm._last_entry_side_by_symbol = {symbol: "BUY" if symbol == "BNBUSDT" else "SELL"}
    fsm._accumulated_fees_by_symbol = {}
    fsm._close_accounting_truth_by_symbol = {}
    fsm._close_fill_trade_ids_by_symbol_order = {}
    fsm._pending_intent_data = {}
    fsm._pending_entry_meta = {}
    fsm._pending_brackets = {}
    fsm._open_regime_by_symbol = {symbol: {"regime": "MEAN_REVERSION"}}
    fsm._open_strategy_by_symbol = {symbol: strategy_id}
    fsm._open_attribution_by_symbol = {
        symbol: {
            "strategy_id": strategy_id,
            "entry_rid": "rid-4686a86078ac92a5" if symbol == "BNBUSDT" else "rid-de5d8de38df998bb",
            "decision_id": "decision-id",
            "intent_id": "intent-id",
            "regime": "MEAN_REVERSION",
        }
    }
    fsm._last_position_closed_ts = {}
    fsm._prev_position_amts = {symbol: float(position_amt)}
    fsm._latest_portfolio_state = {}
    fsm._lifecycle_stats_ledger = None
    fsm.order_index = None
    fsm.fsm.order_index = None
    fsm.order_guardian = None
    fsm.bus = _CaptureBus()
    fsm.get_recent_terminal_close_proof.return_value = None
    fsm._get_async_loop.return_value = None
    fsm._clear_bracket_owner = MagicMock()
    fsm._apply_authoritative_local_close_reset = MagicMock()
    fsm._latest_portfolio_position_amt.return_value = position_amt
    fsm.exposure_guard.state.postfill_reservations = {}
    fsm.exposure_guard.expire_stale.return_value = []
    fsm.exposure_guard.get_exposure_summary.return_value = {}
    fsm.exposure_guard.on_portfolio.return_value = None

    processed: set[str] = set()

    def mark_processed(key: str) -> bool:
        if key in processed:
            return False
        processed.add(key)
        return True

    fsm._mark_processed_event.side_effect = mark_processed
    return fsm


def _fill_event(
    *,
    symbol: str,
    order_id: str,
    client_order_id: str,
    trade_id: str,
    side: str,
    qty: str,
    price: str,
    realized_pnl: str,
    commission: str,
    status: str,
):
    return SimpleNamespace(
        pld={
            "orderId": order_id,
            "exchangeOrderId": order_id,
            "symbol": symbol,
            "quantity": qty,
            "qty": qty,
            "rid": client_order_id,
            "clientOrderId": client_order_id,
            "client_order_id": client_order_id,
            "tradeId": trade_id,
            "trade_id": trade_id,
            "commission": commission,
            "commissionAsset": "USDT",
            "realizedPnl": realized_pnl,
            "price": price,
            "side": side,
            "status": status,
        },
        rid=client_order_id,
    )


def _portfolio_flat_event(symbol: str):
    return SimpleNamespace(pld={"positions": [{"symbol": symbol, "positionAmt": "0"}]})


def _run_fills_and_close(fsm, symbol: str, fills: list[dict]):
    import apps.reference.domains.execution_position.orchestration.event_handlers as handlers_mod

    written: list[dict] = []
    handler = handlers_mod.EPEventHandlers(fsm)
    with patch.object(handlers_mod, "_trade_lifecycle", None), patch.object(
        handlers_mod, "_get_order_logger"
    ) as mock_log_fn, patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
    ) as mock_clock:
        mock_clock.return_value.now_ms.return_value = 1_781_986_511_800
        mock_clock.return_value.now_sec.return_value = 1_781_986.5118
        mock_log_fn.return_value.write.side_effect = written.append
        for fill in fills:
            handler.on_order_fill(_fill_event(symbol=symbol, **fill))
        handler.on_portfolio_state_updated(_portfolio_flat_event(symbol))
    payloads = [
        payload
        for topic, payload, _why, _data_ref, _kwargs in fsm.bus.events
        if topic == "EVT:POSITION_CLOSED"
    ]
    assert len(payloads) == 1
    return written, payloads[0]


BNB_ENTRY_FILLS = [
    {"order_id": "1585961580", "client_order_id": "ENTRY-96ee02ab995a", "trade_id": "140339499", "side": "BUY", "qty": "0.09", "price": "586.720", "realized_pnl": "0", "commission": "0.02112192", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585961580", "client_order_id": "ENTRY-96ee02ab995a", "trade_id": "140339500", "side": "BUY", "qty": "16.18", "price": "586.820", "realized_pnl": "0", "commission": "3.79789904", "status": "FILLED"},
]

BNB_CLOSE_FILLS = [
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339502", "side": "SELL", "qty": "0.01", "price": "585.880", "realized_pnl": "-0.00939446", "commission": "0.00234352", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339503", "side": "SELL", "qty": "0.09", "price": "585.820", "realized_pnl": "-0.08995021", "commission": "0.02108952", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339504", "side": "SELL", "qty": "0.05", "price": "585.820", "realized_pnl": "-0.04997234", "commission": "0.01171640", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339505", "side": "SELL", "qty": "0.02", "price": "585.820", "realized_pnl": "-0.01998893", "commission": "0.00468656", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339506", "side": "SELL", "qty": "0.01", "price": "585.820", "realized_pnl": "-0.00999446", "commission": "0.00234328", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339507", "side": "SELL", "qty": "0.01", "price": "585.820", "realized_pnl": "-0.00999446", "commission": "0.00234328", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339508", "side": "SELL", "qty": "0.03", "price": "585.820", "realized_pnl": "-0.02998340", "commission": "0.00702984", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339509", "side": "SELL", "qty": "0.07", "price": "585.820", "realized_pnl": "-0.06996127", "commission": "0.01640296", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339510", "side": "SELL", "qty": "0.05", "price": "585.820", "realized_pnl": "-0.04997234", "commission": "0.01171640", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339511", "side": "SELL", "qty": "0.05", "price": "585.820", "realized_pnl": "-0.04997234", "commission": "0.01171640", "status": "PARTIALLY_FILLED"},
    {"order_id": "1585962146", "client_order_id": "CLOSE-70fdb18753d5", "trade_id": "140339512", "side": "SELL", "qty": "15.88", "price": "585.810", "realized_pnl": "-16.03001573", "commission": "3.72106512", "status": "FILLED"},
]

ETH_ENTRY_FILLS = [
    {"order_id": "10087856942", "client_order_id": "ENTRY-e0eb8f804579", "trade_id": "292659777", "side": "SELL", "qty": "0.849", "price": "1735.07", "realized_pnl": "0", "commission": "0.58922977", "status": "PARTIALLY_FILLED"},
    {"order_id": "10087856942", "client_order_id": "ENTRY-e0eb8f804579", "trade_id": "292659778", "side": "SELL", "qty": "0.086", "price": "1734.52", "realized_pnl": "0", "commission": "0.05966748", "status": "PARTIALLY_FILLED"},
    {"order_id": "10087856942", "client_order_id": "ENTRY-e0eb8f804579", "trade_id": "292659779", "side": "SELL", "qty": "0.029", "price": "1734.04", "realized_pnl": "0", "commission": "0.02011486", "status": "PARTIALLY_FILLED"},
    {"order_id": "10087856942", "client_order_id": "ENTRY-e0eb8f804579", "trade_id": "292659780", "side": "SELL", "qty": "0.012", "price": "1733.58", "realized_pnl": "0", "commission": "0.00832118", "status": "PARTIALLY_FILLED"},
    {"order_id": "10087856942", "client_order_id": "ENTRY-e0eb8f804579", "trade_id": "292659781", "side": "SELL", "qty": "4.504", "price": "1732.72", "realized_pnl": "0", "commission": "3.12166835", "status": "FILLED"},
]

ETH_CLOSE_FILLS = [
    {"order_id": "10087862542", "client_order_id": "CLOSE-fc34a2f5bcd0", "trade_id": "292659783", "side": "BUY", "qty": "0.012", "price": "1734.74", "realized_pnl": "-0.01942565", "commission": "0.00832675", "status": "PARTIALLY_FILLED"},
    {"order_id": "10087862542", "client_order_id": "CLOSE-fc34a2f5bcd0", "trade_id": "292659784", "side": "BUY", "qty": "0.087", "price": "1734.85", "realized_pnl": "-0.15040601", "commission": "0.06037278", "status": "PARTIALLY_FILLED"},
    {"order_id": "10087862542", "client_order_id": "CLOSE-fc34a2f5bcd0", "trade_id": "292659785", "side": "BUY", "qty": "5.381", "price": "1735.80", "realized_pnl": "-14.41464833", "commission": "3.73613592", "status": "FILLED"},
]


def test_bnb_mean_reversion_multifill_close_aggregates_all_exchange_fills() -> None:
    fsm = _make_mock_fsm("BNBUSDT", position_amt="16.27")
    written, payload = _run_fills_and_close(fsm, "BNBUSDT", BNB_ENTRY_FILLS + BNB_CLOSE_FILLS)

    assert payload["strategy_id"] == "mean_reversion"
    assert payload["realized_pnl"] == pytest.approx(-16.41919994)
    assert payload["fees"] == pytest.approx(7.63147424)
    assert payload["realized_pnl_net"] == pytest.approx(-24.05067418)
    assert payload["close_qty"] == pytest.approx(16.27)
    assert payload["close_commission"] == pytest.approx(3.81245328)
    assert payload["entry_commission"] == pytest.approx(3.81902096)
    assert payload["close_fill_count"] == 11
    assert payload["source_trade_ids"] == [str(i) for i in range(140339502, 140339513)]

    close_write = next(row for row in written if row.get("event_type") == "POSITION_CLOSED")
    assert close_write["metadata"]["close_commission"] == pytest.approx(3.81245328)
    assert close_write["metadata"]["entry_commission"] == pytest.approx(3.81902096)


def test_eth_mean_reversion_multifill_close_aggregates_all_exchange_fills() -> None:
    fsm = _make_mock_fsm("ETHUSDT", position_amt="-5.480")
    _written, payload = _run_fills_and_close(fsm, "ETHUSDT", ETH_ENTRY_FILLS + ETH_CLOSE_FILLS)

    assert payload["strategy_id"] == "mean_reversion"
    assert payload["realized_pnl"] == pytest.approx(-14.58447999)
    assert payload["fees"] == pytest.approx(7.60383709)
    assert payload["realized_pnl_net"] == pytest.approx(-22.18831708)
    assert payload["close_qty"] == pytest.approx(5.480)
    assert payload["close_commission"] == pytest.approx(3.80483545)
    assert payload["entry_commission"] == pytest.approx(3.79900164)
    assert payload["close_fill_count"] == 3
    assert payload["source_trade_ids"] == ["292659783", "292659784", "292659785"]


def test_duplicate_close_trade_id_does_not_double_count_accounting() -> None:
    fsm = _make_mock_fsm("ETHUSDT", position_amt="-5.480")
    fills = ETH_ENTRY_FILLS + ETH_CLOSE_FILLS + [dict(ETH_CLOSE_FILLS[0])]

    _written, payload = _run_fills_and_close(fsm, "ETHUSDT", fills)

    assert payload["realized_pnl"] == pytest.approx(-14.58447999)
    assert payload["close_commission"] == pytest.approx(3.80483545)
    assert payload["close_qty"] == pytest.approx(5.480)
    assert payload["close_fill_count"] == 3
