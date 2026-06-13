from pathlib import Path

from tools.analysis.nrr_rejected_horizon_audit import Bar, assign_episodes, replay_row


def _bar(start_ts_ms: int, open_price: float, high: float, low: float, close: float) -> Bar:
    return Bar(
        close_ts_ms=start_ts_ms + 900_000 - 1,
        open=open_price,
        high=high,
        low=low,
        close=close,
        source_file=Path("fixture.csv").as_posix(),
    )


def test_replay_enters_on_first_full_bar_after_intent() -> None:
    bars = [
        _bar(0, 100.0, 102.0, 99.0, 101.0),
        _bar(900_000, 101.0, 104.0, 100.0, 103.0),
    ]
    row = {
        "timestamp_ms": 1,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "strategy_id": "aurora",
        "nrr_code": "NRR-026",
    }

    outcome = replay_row(row, bars, (1,), cost_bps=10.0)

    assert outcome["entry_ts_ms"] == 900_000
    assert outcome["entry_price"] == 101.0
    assert outcome["h1_status"] == "OK"
    assert outcome["h1_net_bps"] > 0


def test_replay_does_not_jump_across_missing_bars() -> None:
    bars = [
        _bar(0, 100.0, 101.0, 99.0, 100.0),
        _bar(900_000, 100.0, 101.0, 99.0, 100.0),
        _bar(2_700_000, 100.0, 105.0, 99.0, 104.0),
    ]
    row = {
        "timestamp_ms": 1,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "strategy_id": "aurora",
        "nrr_code": "NRR-026",
    }

    outcome = replay_row(row, bars, (1, 2), cost_bps=10.0)

    assert outcome["h1_status"] == "OK"
    assert outcome["h2_status"] == "DATA_GAP"


def test_episode_grouping_separates_signals_after_gap() -> None:
    rows = [
        {"timestamp_ms": 0, "symbol": "ETHUSDT", "side": "BUY", "strategy_id": "aurora", "nrr_code": "NRR-027"},
        {"timestamp_ms": 30 * 60_000, "symbol": "ETHUSDT", "side": "BUY", "strategy_id": "aurora", "nrr_code": "NRR-027"},
        {"timestamp_ms": 91 * 60_000, "symbol": "ETHUSDT", "side": "BUY", "strategy_id": "aurora", "nrr_code": "NRR-027"},
    ]

    assign_episodes(rows, episode_gap_min=60)

    assert rows[0]["episode_id"] == rows[1]["episode_id"]
    assert rows[2]["episode_id"] != rows[1]["episode_id"]
