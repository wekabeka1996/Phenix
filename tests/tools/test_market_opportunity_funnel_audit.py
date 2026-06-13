from tools.analysis.market_opportunity_funnel_audit import (
    Bar,
    attribute_episodes,
    build_candidates,
    group_opportunity_episodes,
)


def _bar(start: int, open_price: float, close: float, high: float | None = None, low: float | None = None) -> Bar:
    return Bar(
        close_ts_ms=start + 900_000 - 1,
        open=open_price,
        high=high if high is not None else max(open_price, close),
        low=low if low is not None else min(open_price, close),
        close=close,
    )


def test_candidates_use_next_bar_open_and_find_long_opportunity() -> None:
    bars = [
        _bar(0, 100.0, 100.0),
        _bar(900_000, 100.0, 101.0, high=101.2, low=99.9),
        _bar(1_800_000, 101.0, 102.0, high=102.2, low=100.8),
    ]

    candidates, tiers = build_candidates({"BTCUSDT": bars}, (1, 2), cost_bps=10.0, threshold_bps=50.0)

    assert candidates[0]["entry_price"] == 100.0
    assert candidates[0]["side"] == "BUY"
    assert candidates[0]["best_horizon_bars"] == 2
    assert tiers["BTCUSDT"]["50"] >= 1


def test_episode_grouping_splits_direction_changes() -> None:
    rows = [
        {"symbol": "SOLUSDT", "side": "BUY", "decision_ts_ms": 0, "exit_ts_ms": 900_000, "best_net_bps": 80.0, "entry_ts_ms": 1, "entry_price": 10.0, "best_horizon_bars": 1, "mfe_bps": 90.0, "mae_bps": -10.0},
        {"symbol": "SOLUSDT", "side": "BUY", "decision_ts_ms": 900_000, "exit_ts_ms": 1_800_000, "best_net_bps": 70.0, "entry_ts_ms": 900_001, "entry_price": 10.1, "best_horizon_bars": 1, "mfe_bps": 80.0, "mae_bps": -15.0},
        {"symbol": "SOLUSDT", "side": "SELL", "decision_ts_ms": 1_800_000, "exit_ts_ms": 2_700_000, "best_net_bps": 60.0, "entry_ts_ms": 1_800_001, "entry_price": 10.2, "best_horizon_bars": 1, "mfe_bps": 70.0, "mae_bps": -20.0},
    ]

    episodes = group_opportunity_episodes(rows)

    assert len(episodes) == 2
    assert episodes[0]["candidate_bars"] == 2
    assert episodes[0]["candidate_end_ts_ms"] == 900_000
    assert episodes[1]["side"] == "SELL"


def test_attribute_marks_md_amr_regime_block_before_intent_bridge() -> None:
    episode = {
        "opportunity_id": 1,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "episode_start_ts_ms": 900_000,
        "candidate_end_ts_ms": 900_000,
        "episode_end_ts_ms": 1_800_000,
        "representative_decision_ts_ms": 900_000,
        "entry_ts_ms": 900_001,
        "entry_price": 100.0,
        "best_horizon_bars": 1,
        "best_net_bps": 80.0,
        "mfe_bps": 90.0,
        "mae_bps": -10.0,
        "candidate_bars": 1,
    }
    trace = {
        "timestamp_ms": 900_000,
        "strategy_id": "md_amr",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "outcome": "SIGNAL",
        "reason": None,
        "regime": "UNCERTAIN",
        "score": 1.0,
        "allowed_regime": False,
        "source_file": "aurora_core.log",
    }

    result = attribute_episodes([episode], [], [trace])[0]

    assert result["classification"] == "ALIGNED_SIGNAL_REGIME_BLOCKED"
    assert result["missed_layer"] == "strategy_regime_gate"
