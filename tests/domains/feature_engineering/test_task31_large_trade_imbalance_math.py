import decimal


def _mk_calc(*, min_trades: int = 2):
    from apps.reference.domains.feature_engineering.large_trade_imbalance import LargeTradeImbalanceCalculator

    return LargeTradeImbalanceCalculator(
        window_ms=60_000,
        min_trades=min_trades,
        eps=decimal.Decimal("1e-12"),
        neutral_value=decimal.Decimal("0.5"),
        use_notional=False,
    )


def test_imbalance_positive_when_buy_volume_dominates():
    calc = _mk_calc(min_trades=2)

    calc.update_trade(ts_ms=1_000, side="sell", qty=1.0, price=100.0)
    calc.update_trade(ts_ms=1_001, side="buy", qty=5.0, price=100.0)

    res = calc.compute(now_ts_ms=1_001)
    assert res.ready is True
    assert res.phi > decimal.Decimal("0.5")


def test_imbalance_negative_when_sell_volume_dominates():
    calc = _mk_calc(min_trades=2)

    calc.update_trade(ts_ms=1_000, side="buy", qty=1.0, price=100.0)
    calc.update_trade(ts_ms=1_001, side="sell", qty=5.0, price=100.0)

    res = calc.compute(now_ts_ms=1_001)
    assert res.ready is True
    assert res.phi < decimal.Decimal("0.5")


def test_imbalance_neutral_and_not_ready_when_insufficient_trades():
    calc = _mk_calc(min_trades=10)

    calc.update_trade(ts_ms=1_000, side="buy", qty=1.0, price=100.0)
    calc.update_trade(ts_ms=1_001, side="sell", qty=1.0, price=100.0)
    calc.update_trade(ts_ms=1_002, side="sell", qty=1.0, price=100.0)

    res = calc.compute(now_ts_ms=1_002)
    assert res.ready is False
    assert res.why == "insufficient_trades"
    assert res.phi == decimal.Decimal("0.5")


def test_imbalance_bounded_range():
    calc = _mk_calc(min_trades=1)

    calc.update_trade(ts_ms=1_000, side="buy", qty=100.0, price=100.0)
    res = calc.compute(now_ts_ms=1_000)

    assert decimal.Decimal("0") <= res.phi <= decimal.Decimal("1")


def test_out_of_order_trade_dropped_counter_increments():
    calc = _mk_calc(min_trades=1)

    calc.update_trade(ts_ms=1_000, side="buy", qty=1.0, price=100.0)
    calc.update_trade(ts_ms=999, side="sell", qty=999.0, price=100.0)  # out-of-order, must drop

    res = calc.compute(now_ts_ms=1_000)
    assert res.dropped_out_of_order == 1

