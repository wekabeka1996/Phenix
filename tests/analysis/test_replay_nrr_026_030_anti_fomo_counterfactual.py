import os
import json
import io
import pytest
from unittest.mock import patch, mock_open
import sys

# Add tools to sys.path so we can import the script
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), '../../tools/analysis')))

import replay_nrr_026_030_anti_fomo_counterfactual as replay


def test_parser_handles_missing_files(tmp_path):
    # Should not crash if logs dir is empty
    traces = replay.load_traces(str(tmp_path))
    assert traces == {}


def test_evaluate_anti_fomo():
    trace_true = {"pm_norm_300s": 15.0}
    missing = []
    assert replay.evaluate_anti_fomo(
        trace_true, "BUY", True, 10.0, missing) == "true"

    trace_nested = {"price_motion_context": {"pm_norm_300s": 15.0}}
    missing = []
    assert replay.evaluate_anti_fomo(
        trace_nested, "BUY", True, 10.0, missing) == "true"

    trace_reject_metadata = {
        "metadata": {
            "low_vol_cost_floor": {
                "price_motion_context": {"pm_norm_300s": 15.0}
            }
        }
    }
    missing = []
    assert replay.evaluate_anti_fomo(
        trace_reject_metadata, "BUY", True, 10.0, missing) == "true"

    missing = []
    assert replay.evaluate_anti_fomo(
        {}, "BUY", False, 10.0, missing) == "disabled"
    assert missing == []

    missing = []
    assert replay.evaluate_anti_fomo(
        trace_true, "BUY", True, None, missing) == "null"
    assert "anti_fomo_sigma_missing" in missing

    missing = []
    assert replay.evaluate_anti_fomo({}, "BUY", True, 10.0, missing) == "null"
    assert "pm_norm_300s_missing" in missing


def test_disabled_gate_marked_correctly():
    ds_cfg = {"nrr026_enabled": False}
    missing = []
    assert replay.evaluate_nrr_026({}, "BUY", ds_cfg, missing) == "disabled"

    pm_cfg = {"enabled": False}
    missing = []
    assert replay.evaluate_nrr_028({}, "BUY", pm_cfg, missing) == "disabled"


def test_find_closest_trace_join_quality():
    traces = [
        {"ts_ms": 1000, "rid": "aurora_A_1000", "side": "BUY"},
        {"ts_ms": 1050, "rid": "aurora_A_1050", "side": "BUY"}
    ]

    # Exact RID match
    entry_exact = {"entry_ts_ms": 1000, "rid": "aurora_A_1000", "side": "BUY"}
    trace, key, quality, delta = replay.find_closest_trace(traces, entry_exact)
    assert key == "rid"
    assert quality == "exact"
    assert delta == 0

    # Time bounded match
    entry_time = {"entry_ts_ms": 1020, "rid": "aurora_A_9999", "side": "BUY"}
    trace, key, quality, delta = replay.find_closest_trace(traces, entry_time)
    assert key == "nearest_timestamp"
    assert quality == "bounded_time"
    assert delta == 20

    # Weak match (outside window)
    entry_weak = {"entry_ts_ms": 90000, "rid": "aurora_A_9999", "side": "BUY"}
    trace, key, quality, delta = replay.find_closest_trace(
        traces, entry_weak, window_ms=100)
    assert quality == "weak"


@patch('replay_nrr_026_030_anti_fomo_counterfactual.load_traces')
@patch('replay_nrr_026_030_anti_fomo_counterfactual.parse_configs')
@patch('os.path.exists')
@patch('replay_nrr_026_030_anti_fomo_counterfactual.open', new_callable=mock_open, create=True)
@patch('csv.DictWriter')
def test_summary_math_correct(mock_writer, mock_open_file, mock_exists, mock_configs, mock_load_traces):
    mock_exists.return_value = True

    mock_configs.return_value = {
        "directional_sanity": {"nrr027_enabled": True, "hard_veto_consecutive_bars": 2},
        "price_motion_sanity": {"enabled": False},
        "anti_fomo_enabled": False,
        "anti_fomo_sigma": 10.0
    }

    mock_load_traces.return_value = {
        "BTCUSDT": [
            {"rid": "id_losing_blocked", "ts_ms": 1000, "side": "BUY",
                "trend_dir": "DOWN", "trend_run_length": 3},
            {"rid": "id_winning_blocked", "ts_ms": 2000, "side": "BUY",
                "trend_dir": "DOWN", "trend_run_length": 3},
            {"rid": "id_losing_not_blocked", "ts_ms": 3000,
                "side": "BUY", "trend_dir": "UP", "trend_run_length": 3},
            {"rid": "id_unresolved_blocked", "ts_ms": 4000,
                "side": "BUY", "trend_dir": "DOWN", "trend_run_length": 3}
        ]
    }

    tl_lines = [
        json.dumps({"symbol": "BTCUSDT", "rid": "id_losing_blocked", "side": "BUY", "event": "closed",
                   "state": "CLOSED", "ts_ms": 1000, "realized_pnl_net": -50.0, "realized_pnl_gross": -49.0}) + "\n",
        json.dumps({"symbol": "BTCUSDT", "rid": "id_winning_blocked", "side": "BUY", "event": "closed",
                   "state": "CLOSED", "ts_ms": 2000, "realized_pnl_net": 100.0, "realized_pnl_gross": 102.0}) + "\n",
        json.dumps({"symbol": "BTCUSDT", "rid": "id_losing_not_blocked", "side": "BUY", "event": "closed",
                   "state": "CLOSED", "ts_ms": 3000, "realized_pnl_net": -20.0, "realized_pnl_gross": -19.0}) + "\n",
        json.dumps({"symbol": "BTCUSDT", "rid": "id_unresolved_blocked", "side": "BUY",
                   "event": "opened", "state": "OPEN", "ts_ms": 4000, "realized_pnl_net": None}) + "\n"
    ]
    mock_open_file.side_effect = [
        io.StringIO("".join(tl_lines)),
        mock_open().return_value,
        mock_open().return_value,
        mock_open().return_value,
    ]

    # Use a side-effect to mock file opening context manager
    # to avoid the iterator exhaustion on multiple opens

    with patch('sys.argv', ['replay_nrr_026_030_anti_fomo_counterfactual.py', '--include-open', 'true']):
        replay.main()


@patch('replay_nrr_026_030_anti_fomo_counterfactual.load_traces')
@patch('replay_nrr_026_030_anti_fomo_counterfactual.parse_configs')
@patch('os.path.exists')
@patch('replay_nrr_026_030_anti_fomo_counterfactual.open', new_callable=mock_open, create=True)
@patch('json.dump')
def test_summary_math_correct_via_json(mock_json_dump, mock_open_file, mock_exists, mock_configs, mock_load_traces):
    mock_exists.return_value = True

    mock_configs.return_value = {
        "directional_sanity": {"nrr027_enabled": True, "hard_veto_consecutive_bars": 2},
        "price_motion_sanity": {"enabled": False},
        "anti_fomo_enabled": False,
        "anti_fomo_sigma": 10.0
    }

    mock_load_traces.return_value = {
        "BTCUSDT": [
            {"rid": "id_losing_blocked", "ts_ms": 1000, "side": "BUY",
                "trend_dir": "DOWN", "trend_run_length": 3},
            {"rid": "id_winning_blocked", "ts_ms": 2000, "side": "BUY",
                "trend_dir": "DOWN", "trend_run_length": 3},
            {"rid": "id_losing_not_blocked", "ts_ms": 3000,
                "side": "BUY", "trend_dir": "UP", "trend_run_length": 3},
            {"rid": "id_unresolved_blocked", "ts_ms": 4000,
                "side": "BUY", "trend_dir": "DOWN", "trend_run_length": 3}
        ]
    }

    tl_lines = [
        json.dumps({"symbol": "BTCUSDT", "rid": "id_losing_blocked", "side": "BUY", "event": "closed",
                   "state": "CLOSED", "ts_ms": 1000, "realized_pnl_net": -50.0, "realized_pnl_gross": -49.0}) + "\n",
        json.dumps({"symbol": "BTCUSDT", "rid": "id_winning_blocked", "side": "BUY", "event": "closed",
                   "state": "CLOSED", "ts_ms": 2000, "realized_pnl_net": 100.0, "realized_pnl_gross": 102.0}) + "\n",
        json.dumps({"symbol": "BTCUSDT", "rid": "id_losing_not_blocked", "side": "BUY", "event": "closed",
                   "state": "CLOSED", "ts_ms": 3000, "realized_pnl_net": -20.0, "realized_pnl_gross": -19.0}) + "\n",
        json.dumps({"symbol": "BTCUSDT", "rid": "id_unresolved_blocked", "side": "BUY",
                   "event": "opened", "state": "OPEN", "ts_ms": 4000, "realized_pnl_net": None}) + "\n"
    ]
    mock_open_file.side_effect = [
        io.StringIO("".join(tl_lines)),
        mock_open().return_value,
        mock_open().return_value,
        mock_open().return_value,
    ]

    with patch('sys.argv', ['replay_nrr_026_030_anti_fomo_counterfactual.py', '--include-open', 'true']):
        replay.main()

    summary = None
    for call in mock_json_dump.call_args_list:
        args, kwargs = call
        if "total_opened_positions" in args[0]:
            summary = args[0]

    assert summary is not None
    assert summary["total_opened_positions"] == 4
    assert summary["total_losing_positions"] == 2
    assert summary["total_winning_positions"] == 1
    assert summary["total_unresolved_positions"] == 1

    assert summary["losing_positions_blocked_by_any_gate"] == 1
    assert summary["winning_positions_blocked_by_any_gate"] == 1
    assert summary["unresolved_positions_blocked_by_any_gate"] == 1

    assert summary["net_loss_avoided_if_blocked"] == 50.0
    assert summary["gross_loss_avoided_if_blocked"] == 49.0
    assert summary["profit_missed_if_blocked"] == 100.0
    assert summary["net_counterfactual_delta"] == - \
        50.0  # avoided loss (50) - missed profit (100)

    assert summary["gate_hit_counts"]["NRR-027"] == 3


@patch('replay_nrr_026_030_anti_fomo_counterfactual.load_traces')
@patch('replay_nrr_026_030_anti_fomo_counterfactual.parse_configs')
@patch('os.path.exists')
@patch('replay_nrr_026_030_anti_fomo_counterfactual.open', new_callable=mock_open, create=True)
def test_main_strict_fails_without_usable_trade_lifecycle_rows(mock_open_file, mock_exists, mock_configs, mock_load_traces):
    mock_exists.return_value = True
    mock_load_traces.return_value = {}
    mock_configs.return_value = {
        "directional_sanity": {},
        "price_motion_sanity": {},
        "anti_fomo_enabled": False,
        "anti_fomo_sigma": None,
    }
    mock_open_file.side_effect = [
        io.StringIO(
            json.dumps({"status": "CLOSED", "symbol": "BTCUSDT",
                       "rid": "unsupported_row"}) + "\n"
        )
    ]

    with patch('sys.argv', ['replay_nrr_026_030_anti_fomo_counterfactual.py']):
        with pytest.raises(SystemExit, match="No usable trade_lifecycle opened/closed rows found"):
            replay.main()
