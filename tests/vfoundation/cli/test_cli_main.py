"""
Tests for vfoundation CLI tool (vfoundation/cli/vfound/__main__.py).

Commands tested: schema, dict lint, dict validate, rfc, replay, trace, simulate, drift.
Uses typer.testing.CliRunner(mix_stderr=False) and tmp_path for all file operations.
"""
from __future__ import annotations

import json
import pathlib
import uuid
from typing import Generator

import pytest
from typer.testing import CliRunner

from vfoundation.cli.vfound.__main__ import app


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def runner() -> CliRunner:
    """CLI runner with separated stderr."""
    return CliRunner()


@pytest.fixture()
def working_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Change CWD to tmp_path so CLI path resolution works correctly."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def dict_files(working_dir: pathlib.Path) -> dict:
    """
    Create valid dictionary YAML files under the working dir.
    Returns paths dict for inspection.
    """
    framework_dir = working_dir / "vfoundation" / "dictionaries"
    app_dir = working_dir / "apps" / "reference" / "dictionaries"
    framework_dir.mkdir(parents=True)
    app_dir.mkdir(parents=True)

    valid_content = {
        "version": "2.2",
        "ops": ["EVAL", "OPEN", "CLOSE"],
        "ttl_profiles": {"standard": 30000, "fast": 5000},
        "security": {"sign_required_ops": ["EVAL"]},
        "limits": {"max_order_size": 100},
    }
    import yaml

    fw_path = framework_dir / "global_v2_2_framework.yaml"
    ap_path = app_dir / "global_v2_2.yaml"
    fw_path.write_text(yaml.dump(valid_content), encoding="utf-8")
    ap_path.write_text(yaml.dump(valid_content), encoding="utf-8")

    return {"framework": fw_path, "app": ap_path}


@pytest.fixture()
def wal_dir(working_dir: pathlib.Path) -> pathlib.Path:
    """Create a wal dir with sample JSONL records including a known RID."""
    wal = working_dir / "ops" / "wal"
    wal.mkdir(parents=True)

    rid = "test-rid-" + uuid.uuid4().hex[:8]
    record = json.dumps({"rid": rid, "op": "ASK", "verb": "EVAL", "why": "test", "_hash": "a" * 64})
    (wal / "wal_001.jsonl").write_text(record + "\n", encoding="utf-8")

    # also write the rid to a marker file for test use
    (working_dir / ".test_rid").write_text(rid, encoding="utf-8")
    return wal


@pytest.fixture()
def adr_template(working_dir: pathlib.Path) -> pathlib.Path:
    """Create docs/ADR-Template.md used by vfound rfc command."""
    docs_dir = working_dir / "docs"
    docs_dir.mkdir(parents=True)
    template = docs_dir / "ADR-Template.md"
    template.write_text(
        "# ADR-XXXX: Title\n\n## Status\nProposed\n\n## Context\n\n## Decision\n\n## Consequences\n",
        encoding="utf-8",
    )
    return template


# ─────────────────────────────────────────────────────────────────────────────
# TestSchemaCommand
# ─────────────────────────────────────────────────────────────────────────────


class TestSchemaCommand:
    """Tests for `vfound schema` command."""

    def test_schema_gen_creates_message_v1_json(
        self, runner: CliRunner, working_dir: pathlib.Path
    ) -> None:
        """schema command should create schemas/message_v1.json."""
        result = runner.invoke(app, ["schema"])
        assert result.exit_code == 0, f"expected exit 0, got {result.exit_code}: {result.output}"
        schema_file = working_dir / "schemas" / "message_v1.json"
        assert schema_file.exists(), "expected schemas/message_v1.json to be created"

    def test_schema_gen_valid_json_schema(
        self, runner: CliRunner, working_dir: pathlib.Path
    ) -> None:
        """Generated schema should be valid JSON with schema structure."""
        runner.invoke(app, ["schema"])
        schema_path = working_dir / "schemas" / "message_v1.json"
        content = json.loads(schema_path.read_text(encoding="utf-8"))
        assert isinstance(content, dict), "expected schema to be a JSON object"
        has_defs = "$defs" in content or "properties" in content
        assert has_defs, "expected schema to have $defs or properties"

    def test_schema_gen_output_message(
        self, runner: CliRunner, working_dir: pathlib.Path
    ) -> None:
        """schema command should print confirmation message."""
        result = runner.invoke(app, ["schema"])
        assert "schemas" in result.output.lower() or "generated" in result.output.lower(), (
            f"expected output to mention schema generation, got: {result.output!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TestDictLint
# ─────────────────────────────────────────────────────────────────────────────


class TestDictLint:
    """Tests for `vfound dict lint` command."""

    def test_dict_lint_global_ok(
        self, runner: CliRunner, dict_files: dict
    ) -> None:
        """dict lint --global with existing files should exit 0 and print OK."""
        result = runner.invoke(app, ["dict", "lint", "--global"])
        assert result.exit_code == 0, f"expected exit 0, got {result.exit_code}: {result.output}"
        assert "OK" in result.output, f"expected 'OK' in output, got: {result.output!r}"

    def test_dict_lint_global_missing_file(
        self, runner: CliRunner, working_dir: pathlib.Path
    ) -> None:
        """dict lint --global without files should exit 1 and print FAIL."""
        result = runner.invoke(app, ["dict", "lint", "--global"])
        assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}"
        assert "FAIL" in result.output, f"expected 'FAIL' in output, got: {result.output!r}"

    def test_dict_lint_domain_ok(
        self, runner: CliRunner, working_dir: pathlib.Path
    ) -> None:
        """dict lint --domain with existing domain dir should exit 0."""
        domain_dir = working_dir / "vfoundation" / "dictionaries" / "domains"
        domain_dir.mkdir(parents=True)
        result = runner.invoke(app, ["dict", "lint", "--domain"])
        assert result.exit_code == 0, f"expected exit 0, got {result.exit_code}: {result.output}"

    def test_dict_lint_domain_missing(
        self, runner: CliRunner, working_dir: pathlib.Path
    ) -> None:
        """dict lint --domain without domain dir should exit 1."""
        result = runner.invoke(app, ["dict", "lint", "--domain"])
        assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}"


# ─────────────────────────────────────────────────────────────────────────────
# TestDictValidate
# ─────────────────────────────────────────────────────────────────────────────


class TestDictValidate:
    """Tests for `vfound dict validate` command."""

    def test_dict_validate_ok(
        self, runner: CliRunner, dict_files: dict
    ) -> None:
        """dict validate with valid files should exit 0 and print OK."""
        result = runner.invoke(app, ["dict", "validate"])
        assert result.exit_code == 0, f"expected exit 0, got {result.exit_code}: {result.output}"
        assert "OK" in result.output

    def test_dict_validate_missing_required_key(
        self, runner: CliRunner, working_dir: pathlib.Path
    ) -> None:
        """dict validate with YAML missing 'version' key should exit 1."""
        import yaml

        framework_dir = working_dir / "vfoundation" / "dictionaries"
        app_dir = working_dir / "apps" / "reference" / "dictionaries"
        framework_dir.mkdir(parents=True)
        app_dir.mkdir(parents=True)

        bad = {"ops": ["EVAL"], "ttl_profiles": {"s": 1000}, "security": {"sign_required_ops": []}, "limits": {}}
        (framework_dir / "global_v2_2_framework.yaml").write_text(yaml.dump(bad))
        (app_dir / "global_v2_2.yaml").write_text(yaml.dump(bad))

        result = runner.invoke(app, ["dict", "validate"])
        assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}"
        assert "version" in result.output or "FAIL" in result.output

    def test_dict_validate_sign_ops_not_subset(
        self, runner: CliRunner, working_dir: pathlib.Path
    ) -> None:
        """sign_required_ops not a subset of ops should trigger error."""
        import yaml

        framework_dir = working_dir / "vfoundation" / "dictionaries"
        app_dir = working_dir / "apps" / "reference" / "dictionaries"
        framework_dir.mkdir(parents=True)
        app_dir.mkdir(parents=True)

        bad = {
            "version": "1.0",
            "ops": ["EVAL"],
            "ttl_profiles": {"standard": 10000},
            "security": {"sign_required_ops": ["NONEXISTENT_VERB"]},
            "limits": {},
        }
        (framework_dir / "global_v2_2_framework.yaml").write_text(yaml.dump(bad))
        (app_dir / "global_v2_2.yaml").write_text(yaml.dump(bad))

        result = runner.invoke(app, ["dict", "validate"])
        assert result.exit_code == 1

    def test_dict_validate_report_json(
        self, runner: CliRunner, dict_files: dict, working_dir: pathlib.Path
    ) -> None:
        """dict validate --report report.json should create JSON report."""
        report_path = working_dir / "report.json"
        result = runner.invoke(app, ["dict", "validate", "--report", str(report_path)])
        assert result.exit_code == 0
        assert report_path.exists(), "expected report.json to be created"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert "ok" in report
        assert "errors" in report

    def test_dict_validate_report_md(
        self, runner: CliRunner, dict_files: dict, working_dir: pathlib.Path
    ) -> None:
        """dict validate --report report.md should create Markdown report."""
        report_path = working_dir / "report.md"
        result = runner.invoke(app, ["dict", "validate", "--report", str(report_path)])
        assert result.exit_code == 0
        content = report_path.read_text(encoding="utf-8")
        assert content.startswith("#"), "expected Markdown report to start with heading"


# ─────────────────────────────────────────────────────────────────────────────
# TestRfcCommand
# ─────────────────────────────────────────────────────────────────────────────


class TestRfcCommand:
    """Tests for `vfound rfc` command."""

    def test_rfc_new_creates_file(
        self, runner: CliRunner, adr_template: pathlib.Path, working_dir: pathlib.Path
    ) -> None:
        """rfc new should create docs/RFC-<name>.md."""
        result = runner.invoke(app, ["rfc", "my-feature"])
        assert result.exit_code == 0, f"expected exit 0, got {result.exit_code}: {result.output}"
        rfc_file = working_dir / "docs" / "RFC-my-feature.md"
        assert rfc_file.exists(), "expected docs/RFC-my-feature.md to be created"

    def test_rfc_new_uses_template(
        self, runner: CliRunner, adr_template: pathlib.Path, working_dir: pathlib.Path
    ) -> None:
        """rfc command should replace ADR-XXXX with RFC-<name> in template."""
        runner.invoke(app, ["rfc", "test-thing"])
        rfc_file = working_dir / "docs" / "RFC-test-thing.md"
        content = rfc_file.read_text(encoding="utf-8")
        assert "RFC-test-thing" in content, f"expected RFC-test-thing in content: {content!r}"
        assert "ADR-XXXX" not in content, "expected ADR-XXXX to be replaced"

    def test_rfc_new_existing_fails(
        self, runner: CliRunner, adr_template: pathlib.Path, working_dir: pathlib.Path
    ) -> None:
        """Calling rfc twice with same name should exit 1 on second call."""
        runner.invoke(app, ["rfc", "duplicate"])
        result2 = runner.invoke(app, ["rfc", "duplicate"])
        assert result2.exit_code == 1
        assert "Exists" in result2.output or "exists" in result2.output.lower()


# ─────────────────────────────────────────────────────────────────────────────
# TestReplayCommand
# ─────────────────────────────────────────────────────────────────────────────


class TestReplayCommand:
    """Tests for `vfound replay` command."""

    def test_replay_existing_rid(
        self, runner: CliRunner, wal_dir: pathlib.Path, working_dir: pathlib.Path
    ) -> None:
        """replay with known RID should exit 0 and create report."""
        rid = (working_dir / ".test_rid").read_text()
        result = runner.invoke(app, ["replay", rid])
        assert result.exit_code == 0, f"expected exit 0, got {result.exit_code}: {result.output}"
        report_files = list((working_dir / "ops" / "reports").glob(f"rid_{rid}.json"))
        assert len(report_files) >= 1, "expected report JSON to be created"
        report = json.loads(report_files[0].read_text())
        assert report["events_count"] > 0

    def test_replay_missing_rid(
        self, runner: CliRunner, wal_dir: pathlib.Path
    ) -> None:
        """replay with unknown RID should exit 1."""
        result = runner.invoke(app, ["replay", "nonexistent-rid-xyz"])
        assert result.exit_code == 1

    def test_replay_no_wal_dir(
        self, runner: CliRunner, working_dir: pathlib.Path
    ) -> None:
        """replay without ops/wal directory should exit 1."""
        result = runner.invoke(app, ["replay", "any-rid"])
        assert result.exit_code == 1

    def test_replay_shadow_mode(
        self, runner: CliRunner, wal_dir: pathlib.Path, working_dir: pathlib.Path
    ) -> None:
        """replay --shadow should include integrity info but no events in report."""
        rid = (working_dir / ".test_rid").read_text()
        result = runner.invoke(app, ["replay", rid, "--shadow"])
        assert result.exit_code == 0
        report_files = list((working_dir / "ops" / "reports").glob(f"rid_{rid}.json"))
        report = json.loads(report_files[0].read_text())
        assert report["shadow_mode"] is True
        assert report["events"] == [], "shadow mode should omit events from report"

    def test_replay_custom_output(
        self, runner: CliRunner, wal_dir: pathlib.Path, working_dir: pathlib.Path
    ) -> None:
        """replay --output should write report to custom path."""
        rid = (working_dir / ".test_rid").read_text()
        custom = working_dir / "my_report.json"
        result = runner.invoke(app, ["replay", rid, "--output", str(custom)])
        assert result.exit_code == 0
        assert custom.exists(), "expected custom output file to be created"


# ─────────────────────────────────────────────────────────────────────────────
# TestTraceCommand
# ─────────────────────────────────────────────────────────────────────────────


class TestTraceCommand:
    """Tests for `vfound trace` command."""

    def test_trace_get_found(
        self, runner: CliRunner, wal_dir: pathlib.Path, working_dir: pathlib.Path
    ) -> None:
        """trace with existing RID should exit 0 and return events list."""
        rid = (working_dir / ".test_rid").read_text()
        result = runner.invoke(app, ["trace", rid])
        assert result.exit_code == 0, f"expected exit 0, got {result.exit_code}: {result.output}"
        data = json.loads(result.output)
        assert data["rid"] == rid
        assert len(data["events"]) > 0

    def test_trace_get_not_found(
        self, runner: CliRunner, wal_dir: pathlib.Path
    ) -> None:
        """trace with unknown RID should exit 0 with empty events."""
        result = runner.invoke(app, ["trace", "nonexistent-rid"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["events"] == []


# ─────────────────────────────────────────────────────────────────────────────
# TestSimulateCommand
# ─────────────────────────────────────────────────────────────────────────────


class TestSimulateCommand:
    """Tests for `vfound simulate` command."""

    def test_simulate_output_message(
        self, runner: CliRunner, working_dir: pathlib.Path
    ) -> None:
        """simulate should print 'Simulated rid=...' to stdout."""
        wal_dir = working_dir / "ops" / "wal"
        wal_dir.mkdir(parents=True)
        sim_file = working_dir / "scenario.json"
        sim_file.write_text("{}", encoding="utf-8")
        result = runner.invoke(app, ["simulate", str(sim_file)])
        assert result.exit_code == 0, f"expected exit 0: {result.output}"
        assert "Simulated rid=" in result.output, (
            f"expected 'Simulated rid=' in output, got: {result.output!r}"
        )

    def test_simulate_creates_wal_entries(
        self, runner: CliRunner, working_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """simulate should create WAL entries with ASK and DEC messages."""
        wal_dir = working_dir / "ops" / "wal"
        wal_dir.mkdir(parents=True)
        sim_file = working_dir / "scenario.json"
        sim_file.write_text("{}", encoding="utf-8")

        # Monkeypatch WAL to write into working_dir
        import vfoundation.dr.wal as wal_mod
        wal_mod.set_wal_dir(wal_dir)

        runner.invoke(app, ["simulate", str(sim_file)])
        wal_files = list(wal_dir.glob("*.jsonl"))
        assert len(wal_files) >= 1, "expected at least one WAL file after simulate"
        lines = wal_files[0].read_text(encoding="utf-8").strip().splitlines()
        ops = [json.loads(line).get("op") for line in lines if line.strip()]
        assert "ASK" in ops, f"expected ASK op in WAL, got ops: {ops}"
        assert "DEC" in ops, f"expected DEC op in WAL, got ops: {ops}"


# ─────────────────────────────────────────────────────────────────────────────
# TestInitCommand — Phase 13.4
# ─────────────────────────────────────────────────────────────────────────────


class TestInitCommand:
    """Tests for `vfound init` domain scaffolding command."""

    def test_init_creates_domain_dir(
        self, runner: CliRunner, working_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init <name> should create apps/reference/domains/<name>/ with __init__.py."""
        import vfoundation.cli.vfound.__main__ as cli_mod
        monkeypatch.setattr(cli_mod, "_cli_root", working_dir)

        result = runner.invoke(app, ["init", "test_domain_alpha"])
        assert result.exit_code == 0, f"expected exit 0, got {result.exit_code}: {result.output}"
        domain_dir = working_dir / "apps" / "reference" / "domains" / "test_domain_alpha"
        assert domain_dir.is_dir(), f"expected domain directory to be created at {domain_dir}"
        assert (domain_dir / "__init__.py").exists(), "expected __init__.py to be created"

    def test_init_creates_main_module(
        self, runner: CliRunner, working_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init <name> should create <name>.py inside the domain directory."""
        import vfoundation.cli.vfound.__main__ as cli_mod
        monkeypatch.setattr(cli_mod, "_cli_root", working_dir)

        runner.invoke(app, ["init", "test_domain_beta"])
        domain_dir = working_dir / "apps" / "reference" / "domains" / "test_domain_beta"
        main_module = domain_dir / "test_domain_beta.py"
        assert main_module.exists(), f"expected {main_module} to be created"
        content = main_module.read_text(encoding="utf-8")
        assert "test_domain_beta" in content, "expected domain name in main module content"

    def test_init_existing_domain_fails(
        self, runner: CliRunner, working_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init on an already-existing domain should exit 1."""
        import vfoundation.cli.vfound.__main__ as cli_mod
        monkeypatch.setattr(cli_mod, "_cli_root", working_dir)

        # Create domain first time — should succeed
        runner.invoke(app, ["init", "test_domain_gamma"])
        # Second call — should fail
        result = runner.invoke(app, ["init", "test_domain_gamma"])
        assert result.exit_code == 1, f"expected exit 1 for existing domain, got {result.exit_code}"

    def test_init_output_message(
        self, runner: CliRunner, working_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init should print 'Created domain:' to stdout."""
        import vfoundation.cli.vfound.__main__ as cli_mod
        monkeypatch.setattr(cli_mod, "_cli_root", working_dir)

        result = runner.invoke(app, ["init", "test_domain_delta"])
        assert result.exit_code == 0, f"expected exit 0, got {result.exit_code}: {result.output}"
        assert "Created domain" in result.output, (
            f"expected 'Created domain' in output, got: {result.output!r}"
        )
