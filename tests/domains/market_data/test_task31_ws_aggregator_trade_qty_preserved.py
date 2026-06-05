import decimal


def test_ws_aggregator_preserves_qty_and_imbalance_is_volume_weighted():
    from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator
    from apps.reference.domains.feature_engineering.large_trade_imbalance import LargeTradeImbalanceCalculator

    symbol = "BTCUSDT"
    agg = WebSocketAggregator(symbols=[symbol], window_seconds=60)

    agg.on_book_ticker(
        symbol=symbol,
        bid_price="99.0",
        bid_size="10",
        ask_price="101.0",
        ask_size="10",
        ts=1_000_000,
    )

    # 100 dust sells (count-dominant), 1 block buy (volume-dominant)
    for i in range(100):
        agg.on_trade(
            symbol=symbol,
            price="100.0",
            quantity="0.01",
            is_buyer_maker=True,  # aggressor SELL
            ts=1_000_000 + i,
            trade_id=i,
        )
    agg.on_trade(
        symbol=symbol,
        price="100.0",
        quantity="5.0",
        is_buyer_maker=False,  # aggressor BUY
        ts=1_000_200,
        trade_id=10_000,
    )

    tick = agg.get_market_tick(symbol)
    assert tick is not None

    assert tick["buy_count"] == 1
    assert tick["sell_count"] == 100
    assert decimal.Decimal(str(tick["buy_volume"])) > decimal.Decimal(str(tick["sell_volume"]))

    calc = LargeTradeImbalanceCalculator(
        window_ms=60_000,
        min_trades=1,
        eps=decimal.Decimal("1e-12"),
        neutral_value=decimal.Decimal("0.5"),
        use_notional=False,
    )
    res = calc.compute_from_tick(tick)
    assert res.ready is True
    assert res.phi > decimal.Decimal("0.5")


def test_ws_aggregator_drops_out_of_order_trade_and_increments_counter():
    from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator

    symbol = "BTCUSDT"
    agg = WebSocketAggregator(symbols=[symbol], window_seconds=60)

    agg.on_book_ticker(
        symbol=symbol,
        bid_price="99.0",
        bid_size="10",
        ask_price="101.0",
        ask_size="10",
        ts=1_000_000,
    )

    agg.on_trade(
        symbol=symbol,
        price="100.0",
        quantity="1.0",
        is_buyer_maker=False,
        ts=1_000_050,
        trade_id=1,
    )
    agg.on_trade(
        symbol=symbol,
        price="100.0",
        quantity="1.0",
        is_buyer_maker=True,
        ts=1_000_040,  # out-of-order (older than last trade)
        trade_id=2,
    )

    tick = agg.get_market_tick(symbol)
    assert tick is not None
    assert tick["trades_dropped_out_of_order"] == 1


def test_ws_aggregator_uses_latest_exchange_ts_for_emitted_tick():
    from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator

    symbol = "BTCUSDT"
    agg = WebSocketAggregator(symbols=[symbol], window_seconds=60)

    agg.on_book_ticker(
        symbol=symbol,
        bid_price="99.0",
        bid_size="10",
        ask_price="101.0",
        ask_size="10",
        ts=1_000_000,
    )
    agg.on_trade(
        symbol=symbol,
        price="100.0",
        quantity="1.0",
        is_buyer_maker=False,
        ts=1_000_250,
        trade_id=1,
    )

    tick = agg.get_market_tick(symbol)
    assert tick is not None
    assert tick["ts"] == 1_000_250


def test_ws_aggregator_ignores_stale_book_timestamp_regression():
    from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator

    symbol = "BTCUSDT"
    agg = WebSocketAggregator(symbols=[symbol], window_seconds=60)

    agg.on_book_ticker(
        symbol=symbol,
        bid_price="99.0",
        bid_size="10",
        ask_price="101.0",
        ask_size="10",
        ts=1_000_300,
    )
    agg.on_trade(
        symbol=symbol,
        price="100.0",
        quantity="1.0",
        is_buyer_maker=False,
        ts=1_000_200,
        trade_id=1,
    )

    first_tick = agg.get_market_tick(symbol)
    assert first_tick is not None
    assert first_tick["ts"] == 1_000_300

    agg.on_book_ticker(
        symbol=symbol,
        bid_price="98.0",
        bid_size="8",
        ask_price="102.0",
        ask_size="12",
        ts=1_000_050,
    )
    agg.on_trade(
        symbol=symbol,
        price="100.5",
        quantity="1.0",
        is_buyer_maker=False,
        ts=1_000_250,
        trade_id=2,
    )

    second_tick = agg.get_market_tick(symbol)
    assert second_tick is not None
    assert second_tick["ts"] == 1_000_300
    assert second_tick["bid"] == "99.0"
    assert second_tick["ask"] == "101.0"

