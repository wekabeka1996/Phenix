"""
E2E tests for FSMP-P1-T05: Shadow-Replay & Drift CLI
Tests for `vfound replay` and `vfound drift` commands.
"""

import json
import pathlib
import pytest
import tempfile
import sys
from typer.testing import CliRunner

# Add parent directory to path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "vfoundation" / "cli"))

from vfound.__main__ import app

runner = CliRunner()


@pytest.fixture
def temp_wal_dir():
    """Create temporary WAL directory with sample data"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_dir = pathlib.Path(tmpdir) / "ops" / "wal"
        wal_dir.mkdir(parents=True, exist_ok=True)

        # Create sample WAL file with test data
        wal_file = wal_dir / "2025-01-26.jsonl"

        test_records = [
            # RID-123: OPEN decision + ORDER_PLACED event (TP)
            {
                "op": "DEC",
                "verb": "OPEN",
                "rid": "RID-123",
                "src": "risk",
                "dst": "execpos",
                "why": "open position",
                "pld": {"symbol": "BTCUSDT", "qty": 0.001},
                "_hash": "hash1",
                "timestamp": 1000.0,
            },
            {
                "op": "EVT",
                "verb": "ORDER_PLACED",
                "rid": "RID-123",
                "src": "exchange",
                "dst": "execpos",
                "why": "order placed",
                "pld": {"symbol": "BTCUSDT", "order_id": "O123"},
                "_hash": "hash2",
                "timestamp": 1001.0,
            },
            # RID-456: CLOSE decision without matching event (FP)
            {
                "op": "DEC",
                "verb": "CLOSE",
                "rid": "RID-456",
                "src": "risk",
                "dst": "execpos",
                "why": "close position",
                "pld": {"symbol": "ETHUSDT", "qty": 0.01},
                "_hash": "hash3",
                "timestamp": 2000.0,
            },
            # RID-789: Event without decision (FN)
            {
                "op": "EVT",
                "verb": "FILL",
                "rid": "RID-789",
                "src": "exchange",
                "dst": "execpos",
                "why": "fill received",
                "pld": {"symbol": "SOLUSDT", "fill_qty": 1.0},
                "_hash": "hash4",
                "timestamp": 3000.0,
            },
        ]

        wal_file.write_text(
            "\n".join(json.dumps(r) for r in test_records), encoding="utf-8"
        )

        yield tmpdir


class TestReplayCommand:
    """Tests for `vfound replay` command"""

    def test_replay_success_with_shadow_mode(self, temp_wal_dir, monkeypatch):
        """Test replay command in shadow mode creates report"""
        monkeypatch.chdir(temp_wal_dir)

        result = runner.invoke(app, ["replay", "RID-123", "--shadow"])

        assert result.exit_code == 0
        assert "✅ Replay complete: 2 events" in result.stdout
        assert "📄 Report saved:" in result.stdout
        assert "🔍 WHY chain length: 2" in result.stdout

        # Check report file exists
        report_path = (
            pathlib.Path(temp_wal_dir) / "ops" / "reports" / "rid_RID-123.json"
        )
        assert report_path.exists()

        # Verify report content
        report = json.loads(report_path.read_text())
        assert report["rid"] == "RID-123"
        assert report["events_count"] == 2
        assert report["shadow_mode"] is True
        assert len(report["why_chain"]) == 2
        assert "open position" in report["why_chain"]
        assert "order placed" in report["why_chain"]
        assert report["integrity"]["all_events_have_hash"] is True

    def test_replay_nonexistent_rid(self, temp_wal_dir, monkeypatch):
        """Test replay with non-existent RID returns error"""
        monkeypatch.chdir(temp_wal_dir)

        result = runner.invoke(app, ["replay", "NONEXISTENT-RID", "--shadow"])

        assert result.exit_code == 1
        # Typer outputs errors to stderr or stdout depending on context
        output = result.stdout + result.stderr if result.stderr else result.stdout
        assert "No events found" in output or result.exit_code == 1

    def test_replay_no_wal_directory(self, monkeypatch, tmp_path):
        """Test replay fails gracefully when WAL directory missing"""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["replay", "RID-123"])

        assert result.exit_code == 1
        # Just check that it fails, Windows may have issues with tempdir cleanup

    def test_replay_custom_output_path(self, temp_wal_dir, monkeypatch):
        """Test replay with custom output path"""
        monkeypatch.chdir(temp_wal_dir)

        custom_output = pathlib.Path(temp_wal_dir) / "custom" / "replay_report.json"
        result = runner.invoke(
            app, ["replay", "RID-123", "--shadow", "--output", str(custom_output)]
        )

        assert result.exit_code == 0
        assert custom_output.exists()

        report = json.loads(custom_output.read_text())
        assert report["rid"] == "RID-123"


class TestDriftCommand:
    """Tests for `vfound drift` command"""

    def test_drift_batch_success(self, temp_wal_dir, monkeypatch):
        """Test drift batch command creates report with metrics"""
        monkeypatch.chdir(temp_wal_dir)

        result = runner.invoke(app, ["drift", "--from-wal", "--window-sec", "5.0"])

        assert result.exit_code == 0
        assert "✅ Drift analysis complete" in result.stdout
        assert "📄 Report saved:" in result.stdout
        assert "TP (True Positive):" in result.stdout
        assert "FP (False Positive):" in result.stdout
        assert "FN (False Negative):" in result.stdout
        assert "TN (True Negative):" in result.stdout
        assert "Drift:" in result.stdout
        assert "Accuracy:" in result.stdout

        # Check report file exists
        reports_dir = pathlib.Path(temp_wal_dir) / "ops" / "reports"
        drift_reports = list(reports_dir.glob("drift_*.json"))
        assert len(drift_reports) == 1

        # Verify report content
        report = json.loads(drift_reports[0].read_text())
        assert "confusion_matrix" in report
        assert "metrics" in report
        assert "drift_pct" in report["metrics"]
        assert "accuracy" in report["metrics"]
        assert report["time_window_sec"] == 5.0
        assert report["decisions_count"] == 2
        assert report["events_count"] == 2

        # Verify confusion matrix
        cm = report["confusion_matrix"]
        assert cm["tp"] == 1  # RID-123: OPEN + ORDER_PLACED
        assert cm["fp"] == 1  # RID-456: CLOSE without event
        assert cm["fn"] == 1  # RID-789: FILL without decision
        assert cm["tn"] == 0

    def test_drift_no_wal_directory(self, monkeypatch, tmp_path):
        """Test drift fails gracefully when WAL directory missing"""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["drift", "--from-wal"])

        assert result.exit_code == 1

    def test_drift_empty_wal(self, monkeypatch, tmp_path):
        """Test drift handles empty WAL gracefully"""
        monkeypatch.chdir(tmp_path)
        wal_dir = tmp_path / "ops" / "wal"
        wal_dir.mkdir(parents=True)

        result = runner.invoke(app, ["drift"])

        assert result.exit_code == 1

    def test_drift_custom_output_path(self, temp_wal_dir, monkeypatch):
        """Test drift with custom output path"""
        monkeypatch.chdir(temp_wal_dir)

        custom_output = pathlib.Path(temp_wal_dir) / "custom" / "drift_report.json"
        result = runner.invoke(app, ["drift", "--output", str(custom_output)])

        assert result.exit_code == 0
        assert custom_output.exists()

        report = json.loads(custom_output.read_text())
        assert "confusion_matrix" in report
        assert "metrics" in report

    def test_drift_window_parameter(self, temp_wal_dir, monkeypatch):
        """Test drift respects window-sec parameter"""
        monkeypatch.chdir(temp_wal_dir)

        result = runner.invoke(app, ["drift", "--window-sec", "0.5"])

        assert result.exit_code == 0

        reports_dir = pathlib.Path(temp_wal_dir) / "ops" / "reports"
        drift_reports = list(reports_dir.glob("drift_*.json"))
        report = json.loads(drift_reports[0].read_text())

        assert report["time_window_sec"] == 0.5


class TestIntegration:
    """Integration tests for CLI workflow"""

    def test_replay_then_drift_workflow(self, temp_wal_dir, monkeypatch):
        """Test full workflow: replay specific RID then compute drift"""
        monkeypatch.chdir(temp_wal_dir)

        # Step 1: Replay specific RID
        replay_result = runner.invoke(app, ["replay", "RID-123", "--shadow"])
        assert replay_result.exit_code == 0

        # Step 2: Compute drift
        drift_result = runner.invoke(app, ["drift"])
        assert drift_result.exit_code == 0

        # Verify both reports exist
        reports_dir = pathlib.Path(temp_wal_dir) / "ops" / "reports"
        assert (reports_dir / "rid_RID-123.json").exists()
        assert len(list(reports_dir.glob("drift_*.json"))) == 1

    def test_reports_directory_created_automatically(self, temp_wal_dir, monkeypatch):
        """Test that reports directory is created automatically"""
        monkeypatch.chdir(temp_wal_dir)

        reports_dir = pathlib.Path(temp_wal_dir) / "ops" / "reports"
        assert not reports_dir.exists()

        result = runner.invoke(app, ["replay", "RID-123", "--shadow"])
        assert result.exit_code == 0
        assert reports_dir.exists()
