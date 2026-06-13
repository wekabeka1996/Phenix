from tools.analysis.strategy_delivery_funnel_audit import build_funnel_rows


def test_build_funnel_separates_regime_and_kelly_blocks() -> None:
    traces = [
        {
            "timestamp_ms": 1_000,
            "strategy_id": "md_amr",
            "symbol": "BTCUSDT",
            "outcome": "SIGNAL",
            "allowed_regime": False,
        },
        {
            "timestamp_ms": 1_000,
            "strategy_id": "mean_reversion",
            "symbol": "ETHUSDT",
            "outcome": "SIGNAL",
            "allowed_regime": True,
        },
    ]
    events = [
        {
            "event": "KELLY_CONFIG_BLOCK",
            "strategy_id": "mean_reversion",
            "symbol": "ETHUSDT",
        }
    ]

    rows = build_funnel_rows(traces, events, [])
    by_key = {(row["strategy_id"], row["symbol"]): row for row in rows}

    assert by_key[("md_amr", "BTCUSDT")]["regime_blocked_core_signals"] == 1
    assert by_key[("mean_reversion", "ETHUSDT")]["kelly_config_blocks"] == 1
