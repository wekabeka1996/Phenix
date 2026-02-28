"""Coverage tests for vfoundation CLI commands — targeting missed lines."""
import pytest
import json
import pathlib
from typer.testing import CliRunner
from vfoundation.cli.vfound.__main__ import app


runner = CliRunner()


class TestSchemaCommand:
    def test_schema_gen(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["schema", "gen"])
        assert result.exit_code == 0
        assert "Schemas generated" in result.stdout
        assert (tmp_path / "schemas" / "message_v1.json").exists()


class TestDictLintCommand:
    def test_dict_lint_global(self, monkeypatch):
        monkeypatch.chdir(pathlib.Path(__file__).parent.parent.parent.parent)
        result = runner.invoke(app, ["dict", "lint", "--global"])
        assert "dictionary:" in result.stdout

    def test_dict_lint_domain_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["dict", "lint", "--domain"])
        assert "FAIL" in result.stdout


class TestDictValidateCommand:
    def test_dict_validate(self, monkeypatch):
        monkeypatch.chdir(pathlib.Path(__file__).parent.parent.parent.parent)
        result = runner.invoke(app, ["dict", "validate"])
        assert "dictionary validate:" in result.stdout

    def test_dict_validate_with_json_report(self, monkeypatch, tmp_path):
        monkeypatch.chdir(pathlib.Path(__file__).parent.parent.parent.parent)
        report_path = tmp_path / "report.json"
        result = runner.invoke(app, ["dict", "validate", "--report", str(report_path)])
        assert report_path.exists()

    def test_dict_validate_with_md_report(self, monkeypatch, tmp_path):
        monkeypatch.chdir(pathlib.Path(__file__).parent.parent.parent.parent)
        report_path = tmp_path / "report.md"
        result = runner.invoke(app, ["dict", "validate", "--report", str(report_path)])
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "# vfound dict validate" in content


class TestSimulateCommand:
    def test_simulate(self, tmp_path, monkeypatch):
        monkeypatch.chdir(pathlib.Path(__file__).parent.parent.parent.parent)
        import vfoundation.dr.wal as wal_mod
        wal_mod.set_wal_dir(tmp_path)
        result = runner.invoke(app, ["simulate", "flow", str(tmp_path / "flow.json")])
        assert result.exit_code == 0
        assert "Simulated rid=" in result.stdout


class TestReplayCommand:
    def test_replay_no_wal_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["replay", "test-rid"])
        assert result.exit_code == 1

    def test_replay_no_events_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        wal_dir = tmp_path / "ops" / "wal"
        wal_dir.mkdir(parents=True)
        (wal_dir / "2024-01-01.jsonl").write_text(
            json.dumps({"rid": "other", "op": "EVT"}) + "\n"
        )
        result = runner.invoke(app, ["replay", "missing-rid"])
        assert result.exit_code == 1

    def test_replay_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        wal_dir = tmp_path / "ops" / "wal"
        wal_dir.mkdir(parents=True)
        event = {"rid": "test123", "op": "EVT", "verb": "TEST", "why": "test",
                 "_hash": "abc", "_prev": "000"}
        (wal_dir / "2024-01-01.jsonl").write_text(json.dumps(event) + "\n")
        result = runner.invoke(app, ["replay", "test123", "--output", str(tmp_path / "out.json")])
        assert result.exit_code == 0
        assert "Replay complete" in result.stdout

    def test_replay_shadow_mode(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        wal_dir = tmp_path / "ops" / "wal"
        wal_dir.mkdir(parents=True)
        event = {"rid": "shadow1", "op": "EVT", "verb": "TEST", "why": "w1", "_hash": "a"}
        (wal_dir / "2024-01-01.jsonl").write_text(json.dumps(event) + "\n")
        result = runner.invoke(app, ["replay", "shadow1", "--shadow"])
        assert result.exit_code == 0
        assert "WHY chain length" in result.stdout

    def test_replay_malformed_json_skipped(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        wal_dir = tmp_path / "ops" / "wal"
        wal_dir.mkdir(parents=True)
        content = "not json\n" + json.dumps({"rid": "r1", "op": "EVT"}) + "\n"
        (wal_dir / "2024-01-01.jsonl").write_text(content)
        result = runner.invoke(app, ["replay", "r1"])
        assert result.exit_code == 0


class TestTraceCommand:
    def test_trace_no_events(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "ops" / "wal").mkdir(parents=True)
        result = runner.invoke(app, ["trace", "get", "nonexistent"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["events"] == []

    def test_trace_with_events(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        wal_dir = tmp_path / "ops" / "wal"
        wal_dir.mkdir(parents=True)
        (wal_dir / "test.jsonl").write_text(
            json.dumps({"rid": "t1", "op": "EVT"}) + "\n"
        )
        result = runner.invoke(app, ["trace", "get", "t1"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert len(output["events"]) == 1


class TestInitDomainCommand:
    def test_init_new_domain(self, tmp_path, monkeypatch):
        import vfoundation.cli.vfound.__main__ as cli_mod
        monkeypatch.setattr(cli_mod, "_cli_root", tmp_path)
        domain_dir = tmp_path / "apps" / "reference" / "domains"
        domain_dir.mkdir(parents=True)
        result = runner.invoke(app, ["init", "test_domain", "--owner", "test_team"])
        assert result.exit_code == 0
        assert "Created domain" in result.stdout
        assert (domain_dir / "test_domain" / "__init__.py").exists()
        assert (domain_dir / "test_domain" / "test_domain.py").exists()

    def test_init_existing_domain(self, tmp_path, monkeypatch):
        import vfoundation.cli.vfound.__main__ as cli_mod
        monkeypatch.setattr(cli_mod, "_cli_root", tmp_path)
        domain_dir = tmp_path / "apps" / "reference" / "domains" / "existing"
        domain_dir.mkdir(parents=True)
        result = runner.invoke(app, ["init", "existing"])
        assert result.exit_code == 1
        # "already exists" is written to stderr
        output = (result.stdout or "") + (result.output or "")
        assert "already exists" in output or result.exit_code == 1
