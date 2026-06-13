from tools.analysis.blocked_strategy_signal_horizon_audit import classify_signals


def test_classify_signal_prefers_regime_and_kelly_evidence() -> None:
    traces = [
        {
            "timestamp_ms": 1_000,
            "observed_at_ms": 1_100,
            "strategy_id": "md_amr",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "outcome": "SIGNAL",
            "allowed_regime": False,
            "regime": "UNCERTAIN",
        },
        {
            "timestamp_ms": 2_000,
            "observed_at_ms": 2_100,
            "strategy_id": "mean_reversion",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "outcome": "SIGNAL",
            "allowed_regime": True,
            "regime": "FLAT_NORMAL",
        },
    ]
    events = [
        {
            "timestamp_ms": 2_101,
            "event": "KELLY_CONFIG_BLOCK",
            "strategy_id": "mean_reversion",
            "symbol": "ETHUSDT",
        }
    ]

    rows = classify_signals(traces, events, [])

    assert rows[0]["block_category"] == "REGIME_ALLOWLIST_BLOCKED"
    assert rows[1]["block_category"] == "KELLY_CONFIG_BLOCKED"
