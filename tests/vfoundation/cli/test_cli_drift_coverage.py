"""Coverage tests for vfoundation CLI commands — drift and more."""
import pytest
import json
import pathlib
from typer.testing import CliRunner
from vfoundation.cli.vfound.__main__ import app

runner = CliRunner()


class TestDriftCommand:
    def test_drift_fails_no_wal_dir(self, tmp_path, monkeypatch):
        import vfoundation.cli.vfound.__main__ as cli_mod
        monkeypatch.setattr(cli_mod, "_cli_root", tmp_path)
        
        # mock drift_monitor
        dm_dir = tmp_path / "apps" / "reference" / "domains" / "execution_position"
        dm_dir.mkdir(parents=True)
        (dm_dir / "drift_monitor.py").write_text("def compute_drift(*args, **kwargs): return args\n")
        
        result = runner.invoke(app, ["drift"])
        assert result.exit_code == 1

    def test_drift_fails_no_drift_monitor(self, tmp_path, monkeypatch):
        import vfoundation.cli.vfound.__main__ as cli_mod
        monkeypatch.setattr(cli_mod, "_cli_root", tmp_path)
        (tmp_path / "ops" / "wal").mkdir(parents=True)
        
        result = runner.invoke(app, ["drift"])
        assert result.exit_code == 1

    def test_drift_no_dec_evt_messages(self, tmp_path, monkeypatch):
        import vfoundation.cli.vfound.__main__ as cli_mod
        monkeypatch.setattr(cli_mod, "_cli_root", tmp_path)

        dm_dir = tmp_path / "apps" / "reference" / "domains" / "execution_position"
        dm_dir.mkdir(parents=True)
        (dm_dir / "drift_monitor.py").write_text("def compute_drift(*args, **kwargs): return args\n")
        
        wal_dir = tmp_path / "ops" / "wal"
        wal_dir.mkdir(parents=True)
        (wal_dir / "empty.jsonl").write_text(json.dumps({"op": "ASK", "verb": "EVAL"}) + "\n")
        
        # Move CWD so reports dir goes to tmp_path
        monkeypatch.chdir(tmp_path)
        
        result = runner.invoke(app, ["drift"])
        assert result.exit_code == 1
        assert "No DEC or EVT messages found" in result.stdout or "No DEC or EVT messages found" in result.stderr

    def test_drift_success(self, tmp_path, monkeypatch):
        import vfoundation.cli.vfound.__main__ as cli_mod
        monkeypatch.setattr(cli_mod, "_cli_root", tmp_path)

        dm_dir = tmp_path / "apps" / "reference" / "domains" / "execution_position"
        dm_dir.mkdir(parents=True)
        
        mock_drift_monitor = """
from collections import namedtuple

class Confusion:
    tp = 1
    fp = 0
    fn = 0
    tn = 0
    drift_pct = 0.0
    accuracy = 100.0

class Mismatch:
    def to_dict(self): return {"test": "ok"}

class Report:
    confusion = Confusion()
    mismatches = [Mismatch()]

def compute_drift(decisions, events_list, time_window_sec):
    return Report()
"""
        (dm_dir / "drift_monitor.py").write_text(mock_drift_monitor)
        
        wal_dir = tmp_path / "ops" / "wal"
        wal_dir.mkdir(parents=True)
        (wal_dir / "data.jsonl").write_text(json.dumps({"op": "DEC", "verb": "OPEN"}) + "\n")
        with (wal_dir / "data.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"op": "EVT", "verb": "FILL"}) + "\n")
        
        monkeypatch.chdir(tmp_path)
        
        result = runner.invoke(app, ["drift"])
        assert result.exit_code == 0
        assert "Drift analysis complete" in result.stdout

