import json
import sys
import os
from unittest.mock import patch
import pytest
from tools.oco_log_to_replay import parse_log_line, main

def test_parse_log_line_valid():
    snapshot = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "position_qty": 1.5,
        "position_cycle_id": 12,
        "orders_snapshot_state": "FRESH",
        "open_brackets": [{"orderId": "123"}],
        "bracket_plan": [{"action_type": "PLACE_SL"}]
    }
    snapshot_str = json.dumps(snapshot)
    
    log_record = {
        "timestamp": "2025-11-24T10:00:00Z",
        "message": "BRACKET_EVAL_SNAPSHOT symbol=BTCUSDT",
        "extra": {
            "snapshot": snapshot_str
        }
    }
    line = json.dumps(log_record)
    
    frame = parse_log_line(line)
    assert frame is not None
    assert frame["ts"] == "2025-11-24T10:00:00Z"
    assert frame["symbol"] == "BTCUSDT"
    assert frame["position_qty"] == 1.5
    assert len(frame["orders"]) == 1
    assert len(frame["bracket_plan"]) == 1

def test_parse_log_line_invalid_json():
    line = "NOT JSON"
    frame = parse_log_line(line)
    assert frame is None

def test_parse_log_line_no_snapshot():
    log_record = {
        "timestamp": "2025-11-24T10:00:00Z",
        "message": "Some other log"
    }
    line = json.dumps(log_record)
    frame = parse_log_line(line)
    assert frame is None

def test_e2e_file_processing(tmp_path):
    # Create input file
    input_file = tmp_path / "input.jsonl"
    output_file = tmp_path / "output.json"
    
    snapshot1 = {"symbol": "BTCUSDT", "side": "LONG", "position_qty": 1.0}
    snapshot2 = {"symbol": "ETHUSDT", "side": "SHORT", "position_qty": 10.0}
    
    lines = [
        json.dumps({"timestamp": "2025-01-01T10:00:00Z", "message": "Log 1", "extra": {"snapshot": json.dumps(snapshot1)}}),
        json.dumps({"timestamp": "2025-01-01T10:00:01Z", "message": "Log 2", "extra": {"snapshot": json.dumps(snapshot2)}}),
        json.dumps({"timestamp": "2025-01-01T10:00:02Z", "message": "Log 3"}) # No snapshot
    ]
    
    input_file.write_text("\n".join(lines), encoding="utf-8")
    
    # Run script via CLI args simulation
    test_args = ["oco_log_to_replay.py", "--runtime-logs", str(input_file), "--out", str(output_file)]
    
    with patch.object(sys, 'argv', test_args):
        main()
        
    assert output_file.exists()
    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["symbol"] == "BTCUSDT"
    assert data[1]["symbol"] == "ETHUSDT"
