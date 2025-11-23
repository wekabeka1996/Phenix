"""
Tests for TCA CLI
=================
"""
import pytest
import sys
import json
from unittest.mock import patch, MagicMock
from tools.tca_execpos_cli import main

@pytest.fixture
def mock_compute():
    with patch("tools.tca_execpos_cli.compute_tca_for_period") as m:
        yield m

def test_cli_basic_invocation(mock_compute, tmp_path):
    """Test basic CLI invocation with JSON output."""
    # Mock return value
    mock_compute.return_value = {
        "records": [{"trade_id": "t1"}],
        "summaries": [{
            "scope": "GLOBAL", 
            "total_volume": 100.0,
            "total_fees": 0.0,
            "trade_count": 1,
            "avg_slippage_bps": 0.0,
            "p95_slippage_bps": 0.0,
            "avg_time_to_fill_ms": 0.0
        }]
    }
    
    output_json = tmp_path / "report.json"
    
    # Simulate command line args
    test_args = [
        "tools/tca_execpos_cli.py",
        "--logs-root", str(tmp_path),
        "--from-ts", "2023-01-01T00:00:00Z",
        "--to-ts", "2023-01-02T00:00:00Z",
        "--output-json", str(output_json)
    ]
    
    with patch.object(sys, "argv", test_args):
        main()
        
    # Verify compute called with correct args
    mock_compute.assert_called_once()
    call_kwargs = mock_compute.call_args[1]
    assert call_kwargs["logs_root"] == str(tmp_path)
    assert call_kwargs["from_ts"] == 1672531200.0 # 2023-01-01 UTC
    
    # Verify JSON output
    assert output_json.exists()
    with open(output_json) as f:
        data = json.load(f)
        assert len(data["records"]) == 1
        assert data["summaries"][0]["total_volume"] == 100.0

def test_cli_summary_output(mock_compute, tmp_path, capsys):
    """Test CLI summary output to stdout and file."""
    mock_compute.return_value = {
        "records": [],
        "summaries": [
            {
                "scope": "BTCUSDT",
                "total_volume": 50000.0,
                "total_fees": 5.0,
                "trade_count": 1,
                "avg_slippage_bps": -2.5,
                "p95_slippage_bps": -10.0,
                "avg_time_to_fill_ms": 150.0
            }
        ]
    }
    
    output_summary = tmp_path / "summary.txt"
    
    test_args = [
        "tools/tca_execpos_cli.py",
        "--logs-root", str(tmp_path),
        "--from-ts", "2023-01-01T00:00:00Z",
        "--to-ts", "2023-01-02T00:00:00Z",
        "--output-summary", str(output_summary)
    ]
    
    with patch.object(sys, "argv", test_args):
        main()
        
    # Verify stdout
    captured = capsys.readouterr()
    assert "BTCUSDT" in captured.out
    assert "50000.00" in captured.out
    
    # Verify file output
    assert output_summary.exists()
    content = output_summary.read_text()
    assert "BTCUSDT" in content
    assert "50000.00" in content
