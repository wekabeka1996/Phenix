from tools.analysis.signal_terminal_outcome_audit import build_audit


def test_build_audit_collapses_lifecycle_to_latest_terminal_outcome() -> None:
    rows = [
        {
            "rid": "r1",
            "event_type": "STRATEGY_SIGNAL_PRODUCED",
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "timestamp": 1,
        },
        {
            "rid": "r1",
            "event_type": "ORDER_INTENT",
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "timestamp": 2,
        },
        {
            "rid": "r1",
            "event_type": "ORDER_FILLED",
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "timestamp": 3,
        },
        {
            "rid": "r2",
            "event_type": "STRATEGY_SIGNAL_PRODUCED",
            "strategy_id": "mean_reversion",
            "symbol": "SOLUSDT",
            "side": "SELL",
            "timestamp": 4,
        },
        {
            "rid": "r2",
            "event_type": "STRATEGY_DECISION_BLOCKED",
            "strategy_id": "mean_reversion",
            "symbol": "SOLUSDT",
            "reason_code": "AUTHORITY_MODE_SHADOW",
            "metadata": {"terminal_outcome": "shadowed"},
            "timestamp": 5,
        },
        {
            "rid": "r3",
            "event_type": "STRATEGY_SIGNAL_PRODUCED",
            "strategy_id": "aurora",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "timestamp": 6,
        },
    ]

    audit_rows, summary = build_audit(rows)
    by_rid = {row["rid"]: row for row in audit_rows}

    assert by_rid["r1"]["terminal_outcome"] == "filled"
    assert by_rid["r1"]["lifecycle_outcomes"] == ["filled", "intent"]
    assert by_rid["r2"]["terminal_outcome"] == "shadowed"
    assert by_rid["r3"]["terminal_outcome"] is None
    assert summary["terminal_coverage_pct"] == 66.6667
    assert summary["attribution_coverage_pct"] == 100.0
