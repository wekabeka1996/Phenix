from __future__ import annotations

import decimal
import time
from unittest.mock import MagicMock

from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from vfoundation.core.protocol import Message


def _build_config():
    config = MagicMock()

    pt_config = MagicMock()
    pt_config.enable_market_tick_subscription = False

    precision = MagicMock()
    precision.quantity_min_threshold = 0.0001
    precision.flat_position_threshold = 0.0001
    precision.decimal_places = 4
    pt_config.precision = precision

    domains = MagicMock()
    domains.position_tracking = pt_config
    config.domains = domains

    exposure = MagicMock()
    exposure.leverage_defaults = {"__default__": "10.0"}

    execution = MagicMock()
    execution.exposure = exposure

    trading = MagicMock()
    trading.execution = execution
    config.trading = trading

    btcusdt_spec = MagicMock()
    btcusdt_spec.execution.target_leverage = 20
    config.instruments = {"BTCUSDT": btcusdt_spec}

    return config


def _tracker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fsm = MagicMock()
    fsm.listen = MagicMock()
    fsm.emit = MagicMock()

    tracker = PositionTracking(fsm, _build_config())
    tracker._write_wal_record = MagicMock(return_value="wal-hash")
    return tracker, fsm


def _market_tick(symbol: str, price: str) -> Message:
    return Message(
        op="EVT",
        verb="EVT:MARKET_TICK_RECEIVED",
        pld={"symbol": symbol, "price": price, "ts": int(time.time() * 1000)},
        src="market_data",
        dst="position_tracking",
        rid="tick-rid",
    )


def _trade_event(*, side: str, price: str = "100.0") -> Message:
    return Message(
        op="EVT",
        verb="EVT:TRADE_EXECUTED",
        pld={
            "symbol": "BTCUSDT",
            "side": side,
            "price": price,
            "quantity": "1.0",
            "fees": "0.0",
            "venue": "binance",
            "ts": int(time.time() * 1000),
        },
        src="execution",
        dst="position_tracking",
        rid="trade-rid",
    )


def _account_update_event(*, positions, total_unrealized_profit: str) -> Message:
    return Message(
        op="EVT",
        verb="EVT:ACCOUNT_UPDATE_RECEIVED",
        pld={
            "totalWalletBalance": "10000",
            "totalUnrealizedProfit": total_unrealized_profit,
            "totalCrossWalletBalance": "9990",
            "positions": positions,
            "updateTime": int(time.time() * 1000),
        },
        src="account_balance",
        dst="position_tracking",
        rid="account-rid",
    )


def test_trade_emission_exports_symbol_economics_for_long_position(tmp_path, monkeypatch):
    tracker, fsm = _tracker(tmp_path, monkeypatch)

    tracker.on_market_tick(_market_tick("BTCUSDT", "110.0"))
    tracker.on_trade_executed(_trade_event(side="buy"))

    payload = fsm.emit.call_args.kwargs["payload"]
    position = payload["positions"][0]

    assert decimal.Decimal(position["net_position"]) == decimal.Decimal("1.0")
    assert decimal.Decimal(position["markPrice"]) == decimal.Decimal("110.0")
    assert decimal.Decimal(
        position["unrealizedPnl"]) == decimal.Decimal("10.00")
    assert decimal.Decimal(
        position["unrealizedPnlPct"]) == decimal.Decimal("10.00")


def test_trade_emission_exports_symbol_economics_for_short_position(tmp_path, monkeypatch):
    tracker, fsm = _tracker(tmp_path, monkeypatch)

    tracker.on_market_tick(_market_tick("BTCUSDT", "90.0"))
    tracker.on_trade_executed(_trade_event(side="sell"))

    payload = fsm.emit.call_args.kwargs["payload"]
    position = payload["positions"][0]

    assert decimal.Decimal(position["net_position"]) == decimal.Decimal("-1.0")
    assert decimal.Decimal(position["markPrice"]) == decimal.Decimal("90.0")
    assert decimal.Decimal(
        position["unrealizedPnl"]) == decimal.Decimal("10.00")
    assert decimal.Decimal(
        position["unrealizedPnlPct"]) == decimal.Decimal("10.00")


def test_trade_emission_leaves_economics_null_when_mark_price_unavailable(tmp_path, monkeypatch):
    tracker, fsm = _tracker(tmp_path, monkeypatch)

    tracker.on_trade_executed(_trade_event(side="buy"))

    payload = fsm.emit.call_args.kwargs["payload"]
    position = payload["positions"][0]

    assert position["markPrice"] is None
    assert position["unrealizedPnl"] is None
    assert position["unrealizedPnlPct"] is None


def test_account_update_exports_authoritative_symbol_economics_for_long_position(tmp_path, monkeypatch):
    tracker, fsm = _tracker(tmp_path, monkeypatch)

    tracker.on_account_update(
        _account_update_event(
            positions=[{
                "symbol": "BTCUSDT",
                "positionAmt": "1.0",
                "entryPrice": "100.0",
                "markPrice": "110.0",
                "unRealizedProfit": "10.0",
                "leverage": 20,
                "marginType": "cross",
            }],
            total_unrealized_profit="10.0",
        )
    )

    payload = fsm.emit.call_args.kwargs["payload"]
    position = payload["positions"][0]

    assert decimal.Decimal(
        payload["unrealized_pnl"]) == decimal.Decimal("10.00")
    assert decimal.Decimal(position["markPrice"]) == decimal.Decimal("110.0")
    assert decimal.Decimal(
        position["unrealizedPnl"]) == decimal.Decimal("10.00")
    assert decimal.Decimal(
        position["unrealizedPnlPct"]) == decimal.Decimal("10.00")


def test_account_update_explicit_alias_mapping_preserves_mark_price_and_unrealized_profit(tmp_path, monkeypatch):
    tracker, fsm = _tracker(tmp_path, monkeypatch)

    tracker.on_account_update(
        _account_update_event(
            positions=[{
                "symbol": "ETHUSDT",
                "positionAmt": "1.0",
                "entryPrice": "100.0",
                "mark_price": "120.0",
                "unrealizedProfit": "20.0",
                "leverage": 20,
                "marginType": "cross",
            }],
            total_unrealized_profit="20.0",
        )
    )

    payload = fsm.emit.call_args.kwargs["payload"]
    position = payload["positions"][0]

    assert decimal.Decimal(position["markPrice"]) == decimal.Decimal("120.0")
    assert decimal.Decimal(
        position["unrealizedPnl"]) == decimal.Decimal("20.00")
    assert decimal.Decimal(
        position["unrealizedPnlPct"]) == decimal.Decimal("20.00")


def test_account_update_leaves_economics_null_when_source_missing(tmp_path, monkeypatch):
    tracker, fsm = _tracker(tmp_path, monkeypatch)

    tracker.on_account_update(
        _account_update_event(
            positions=[{
                "symbol": "XRPUSDT",
                "positionAmt": "1.0",
                "entryPrice": "100.0",
                "leverage": 20,
                "marginType": "cross",
            }],
            total_unrealized_profit="0.0",
        )
    )

    payload = fsm.emit.call_args.kwargs["payload"]
    position = payload["positions"][0]

    assert position["markPrice"] is None
    assert position["unrealizedPnl"] is None
    assert position["unrealizedPnlPct"] is None
