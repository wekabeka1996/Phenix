import json

import pytest

from tools.analysis.profitability_recovery_replay import (
    aggregate,
    chronological_fold,
    load_rejects,
    replay_tpsl,
)
from tools.analysis.nrr_rejected_horizon_audit import Bar


def test_load_rejects_joins_signal_geometry_by_rid(tmp_path) -> None:
    path = tmp_path / "order_log_v1.jsonl"
    rows = [
        {
            "rid": "r1",
            "event_type": "STRATEGY_SIGNAL_PRODUCED",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "strategy_id": "md_amr",
            "metadata": {
                "entry_price": 2000.0,
                "stop_price": 1980.0,
                "target_price": 2040.0,
            },
            "timestamp": 1000,
        },
        {
            "rid": "r1",
            "event_type": "DECISION_INTENT_REJECTED",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "strategy_id": "md_amr",
            "nrr_code": "NRR-027",
            "regime": "TREND_UP",
            "timestamp": 2000,
        },
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    rejects = load_rejects([path], start_ms=0, end_ms=3000)

    assert rejects[0]["entry_price"] == 2000.0
    assert rejects[0]["stop_price"] == 1980.0
    assert rejects[0]["target_price"] == 2040.0


def test_chronological_fold_labels_post_forward_window() -> None:
    assert chronological_fold(
        11_000,
        start_ms=0,
        end_ms=10_000,
        embargo_ms=0,
        forward_end_ms=12_000,
    ) == "post_forward"


def test_replay_tpsl_uses_first_touch_and_real_geometry() -> None:
    bars = [
        Bar(
            close_ts_ms=1_700_000_899_999,
            open=2000.0,
            high=2045.0,
            low=1990.0,
            close=2030.0,
            source_file="test.csv",
        )
    ]

    result = replay_tpsl(
        {"side": "BUY", "stop_price": 1980.0, "target_price": 2040.0},
        bars=bars,
        entry_ts_ms=bars[0].start_ts_ms,
        entry_price=2000.0,
        horizon_bars=1,
        cost_bps=15.0,
    )

    assert result["tpsl_status"] == "TP_HIT"
    assert result["tpsl_net_bps"] == pytest.approx(185.0)


def test_replay_tpsl_rejects_geometry_invalid_at_next_bar_entry() -> None:
    bars = [
        Bar(
            close_ts_ms=1_700_000_899_999,
            open=2050.0,
            high=2060.0,
            low=2040.0,
            close=2055.0,
            source_file="test.csv",
        )
    ]

    result = replay_tpsl(
        {"side": "BUY", "stop_price": 1980.0, "target_price": 2040.0},
        bars=bars,
        entry_ts_ms=bars[0].start_ts_ms,
        entry_price=2050.0,
        horizon_bars=1,
        cost_bps=15.0,
    )

    assert result["tpsl_status"] == "GEOMETRY_INVALID_AT_REPLAY_ENTRY"


def test_replay_tpsl_assumes_stop_when_tp_and_sl_touch_same_bar() -> None:
    bars = [
        Bar(
            close_ts_ms=1_700_000_899_999,
            open=2000.0,
            high=2050.0,
            low=1970.0,
            close=2030.0,
            source_file="test.csv",
        )
    ]

    result = replay_tpsl(
        {"side": "BUY", "stop_price": 1980.0, "target_price": 2040.0},
        bars=bars,
        entry_ts_ms=bars[0].start_ts_ms,
        entry_price=2000.0,
        horizon_bars=1,
        cost_bps=15.0,
    )

    assert result["tpsl_status"] == "AMBIGUOUS_BOTH_TOUCHED_STOP_ASSUMED"
    assert result["tpsl_net_bps"] == pytest.approx(-115.0)


def test_fee_gross_ratio_uses_fees_from_gross_positive_episodes_only() -> None:
    rows = [
        {
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "side": "BUY",
            "nrr_code": "NRR-027",
            "cost_bps": 10.0,
            "horizon_bars": 1,
            "fold": "validation",
            "entry_utc": "2026-06-10T00:00:00+00:00",
            "gross_bps": 40.0,
            "net_bps": 30.0,
        },
        {
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "side": "BUY",
            "nrr_code": "NRR-027",
            "cost_bps": 10.0,
            "horizon_bars": 1,
            "fold": "validation",
            "entry_utc": "2026-06-10T01:00:00+00:00",
            "gross_bps": -20.0,
            "net_bps": -30.0,
        },
    ]

    summary = aggregate(rows)[0]

    assert summary["fee_bps_total"] == 20.0
    assert summary["fee_bps_gross_positive"] == 10.0
    assert summary["fee_gross_ratio"] == pytest.approx(0.25)
