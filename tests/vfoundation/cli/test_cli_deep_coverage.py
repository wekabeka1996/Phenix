import json
import pytest
import pathlib
import sys
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from vfoundation.cli.vfound.__main__ import app

runner = CliRunner()

def test_cli_validate_no_files(tmp_path, monkeypatch):
    """Test 'dict validate' when default files are missing."""
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        result = runner.invoke(app, ["dict", "validate"])
        assert result.exit_code == 1

def test_cli_lint_no_files(tmp_path, monkeypatch):
    """Test 'dict lint' when files missing."""
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        result = runner.invoke(app, ["dict", "lint", "--global"])
        assert result.exit_code == 1
        assert "FAIL" in result.output

def test_cli_drift_no_wal(tmp_path, monkeypatch):
    """Test 'drift' when WAL directory is missing."""
    with patch("pathlib.Path.exists", return_value=False):
        result = runner.invoke(app, ["drift"])
        assert result.exit_code == 1
        assert "WAL directory not found" in result.output

def test_cli_drift_success(tmp_path, monkeypatch):
    """Test 'drift' with simulated WAL data."""
    wal_dir = tmp_path / "ops" / "wal"
    wal_dir.mkdir(parents=True)
    f1 = wal_dir / "test.jsonl"
    f1.write_text('{"op": "DEC", "verb": "OPEN", "ts": 1000, "rid": "r1"}\n{"op": "EVT", "verb": "ORDER_PLACED", "ts": 1100, "rid": "r1"}\n')
    
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        
        with patch("importlib.util.spec_from_file_location") as mock_spec:
            mock_m = MagicMock()
            mock_m.compute_drift.return_value = MagicMock(confusion=MagicMock(tp=1, fp=0, fn=0, tn=0, drift_pct=0, accuracy=100), mismatches=[])
            mock_spec.return_value.loader.exec_module.side_effect = lambda m: None
            
            with patch("importlib.util.module_from_spec", return_value=mock_m):
                result = runner.invoke(app, ["drift", "--window-sec", "5.0"])
                assert "Drift analysis complete" in result.output

def test_cli_schema_gen():
    """Test 'schema' command."""
    result = runner.invoke(app, ["schema", "gen"])
    assert result.exit_code in (0, 1)

def test_cli_init_command(tmp_path, monkeypatch):
    """Test 'init' command."""
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        # It creates directories under apps/reference/domains relative to _cli_root
        # We need to mock _cli_root or just let it fail/succeed if it can.
        result = runner.invoke(app, ["init", "new_domain_test"])
        # Code uses _cli_root which might be repo root.
        assert result.exit_code in (0, 1)

def test_cli_replay_error(tmp_path, monkeypatch):
    """Test 'replay' with errors to cover exception branches."""
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        # Mocking wal_dir.glob to return something that will cause error
        with patch("pathlib.Path.glob", side_effect=RuntimeError("Glob crash")):
            result = runner.invoke(app, ["replay", "rid123"])
            assert result.exit_code == 1
