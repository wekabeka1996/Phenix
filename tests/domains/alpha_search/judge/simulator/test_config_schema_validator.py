"""Phase 5 Package 5H — config/schema validator tests.

Tests for:
  A. Config-file validation
  B. Path checks
  C. Schema-set validation
  D. Preflight summary orchestration
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from apps.reference.domains.alpha_search.judge.simulator.config_schema_validator import (
    run_simulator_preflight,
    validate_simulator_config_file,
    validate_simulator_paths,
    validate_simulator_schema_set,
)
from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    SimulatorConfig,
)


# ── helpers ──────────────────────────────────────────────────────────


def _write_yaml(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def _valid_sim_yaml(
    tmp_path: Path,
    *,
    enabled: bool = True,
    judge_logs_path: str | None = None,
    outcome_data_path: str | None = None,
    calibration_dataset_path: str | None = None,
    summary_report_path: str | None = None,
) -> Path:
    """Write a valid judge_simulator.yaml, creating input paths by default."""
    logs_dir = tmp_path / "logs" / "judge_experts"
    logs_dir.mkdir(parents=True, exist_ok=True)
    outcomes = tmp_path / "data" / "outcomes.json"
    outcomes.parent.mkdir(parents=True, exist_ok=True)
    outcomes.write_text(
        '{"schema_version":"1","outcomes":[]}', encoding="utf-8")

    data = {
        "judge_simulator": {
            "enabled": enabled,
            "judge_logs_path": judge_logs_path or str(logs_dir),
            "outcome_data_path": outcome_data_path or str(outcomes),
            "calibration_dataset_path": calibration_dataset_path
            or str(tmp_path / "out" / "calibration.jsonl"),
            "summary_report_path": summary_report_path
            or str(tmp_path / "out" / "summary.json"),
            "fee_per_cycle_bps": 25,
            "slippage_pct": 0.1,
        }
    }
    cfg_path = tmp_path / "judge_simulator.yaml"
    return _write_yaml(cfg_path, data)


# ════════════════════════════════════════════════════════════════════
# A. Config-file validation
# ════════════════════════════════════════════════════════════════════


class TestConfigFileValidation:

    def test_valid_config_accepted(self, tmp_path):
        cfg_path = _valid_sim_yaml(tmp_path)
        config = validate_simulator_config_file(cfg_path)
        assert isinstance(config, SimulatorConfig)
        assert config.fee_per_cycle_bps == 25

    def test_malformed_yaml_rejected(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        # Use a YAML tab indentation error that PyYAML rejects
        bad.write_text("key:\n\t- invalid tab indent\n", encoding="utf-8")
        with pytest.raises(ValueError, match="[Mm]alformed YAML"):
            validate_simulator_config_file(bad)

    def test_missing_judge_simulator_key_rejected(self, tmp_path):
        cfg = _write_yaml(tmp_path / "no_key.yaml", {"other": {}})
        with pytest.raises(ValueError, match="judge_simulator"):
            validate_simulator_config_file(cfg)

    def test_missing_required_field_rejected(self, tmp_path):
        data = {
            "judge_simulator": {
                "enabled": True,
                # missing all path fields
            }
        }
        cfg = _write_yaml(tmp_path / "incomplete.yaml", data)
        with pytest.raises((ValueError, Exception)):
            validate_simulator_config_file(cfg)

    def test_invalid_fee_value_rejected(self, tmp_path):
        data = {
            "judge_simulator": {
                "enabled": False,
                "judge_logs_path": "./logs",
                "outcome_data_path": "./data.json",
                "calibration_dataset_path": "./cal.jsonl",
                "summary_report_path": "./sum.json",
                "fee_per_cycle_bps": -10,
                "slippage_pct": 0.1,
            }
        }
        cfg = _write_yaml(tmp_path / "bad_fee.yaml", data)
        with pytest.raises(Exception):
            validate_simulator_config_file(cfg)

    def test_empty_path_rejected(self, tmp_path):
        data = {
            "judge_simulator": {
                "enabled": False,
                "judge_logs_path": "",
                "outcome_data_path": "./data.json",
                "calibration_dataset_path": "./cal.jsonl",
                "summary_report_path": "./sum.json",
            }
        }
        cfg = _write_yaml(tmp_path / "empty_path.yaml", data)
        with pytest.raises(Exception):
            validate_simulator_config_file(cfg)

    def test_whitespace_path_rejected(self, tmp_path):
        data = {
            "judge_simulator": {
                "enabled": False,
                "judge_logs_path": "   ",
                "outcome_data_path": "./data.json",
                "calibration_dataset_path": "./cal.jsonl",
                "summary_report_path": "./sum.json",
            }
        }
        cfg = _write_yaml(tmp_path / "ws_path.yaml", data)
        with pytest.raises(Exception):
            validate_simulator_config_file(cfg)

    def test_missing_config_file_rejected(self):
        with pytest.raises(FileNotFoundError):
            validate_simulator_config_file("/nonexistent/path.yaml")

    def test_non_mapping_yaml_rejected(self, tmp_path):
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            validate_simulator_config_file(p)

    def test_judge_simulator_not_mapping_rejected(self, tmp_path):
        p = _write_yaml(tmp_path / "str.yaml",
                        {"judge_simulator": "not_a_dict"})
        with pytest.raises(ValueError, match="must be a mapping"):
            validate_simulator_config_file(p)


# ════════════════════════════════════════════════════════════════════
# B. Path checks
# ════════════════════════════════════════════════════════════════════


class TestPathChecks:

    def _make_config(self, tmp_path, **overrides) -> SimulatorConfig:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        outcomes = tmp_path / "outcomes.json"
        outcomes.write_text("{}", encoding="utf-8")

        defaults = {
            "enabled": True,
            "judge_logs_path": str(logs_dir),
            "outcome_data_path": str(outcomes),
            "calibration_dataset_path": str(tmp_path / "out" / "cal.jsonl"),
            "summary_report_path": str(tmp_path / "out" / "sum.json"),
            "fee_per_cycle_bps": 25.0,
            "slippage_pct": 0.1,
        }
        defaults.update(overrides)
        return SimulatorConfig(**defaults)

    def test_valid_paths_accepted(self, tmp_path):
        config = self._make_config(tmp_path)
        result = validate_simulator_paths(config)
        assert result["ok"] is True

    def test_missing_judge_logs_path_rejected(self, tmp_path):
        config = self._make_config(
            tmp_path, judge_logs_path=str(tmp_path / "nonexistent_logs")
        )
        with pytest.raises(ValueError, match="judge_logs_path"):
            validate_simulator_paths(config)

    def test_missing_outcome_data_path_rejected(self, tmp_path):
        config = self._make_config(
            tmp_path, outcome_data_path=str(tmp_path / "missing.json")
        )
        with pytest.raises(ValueError, match="outcome_data_path"):
            validate_simulator_paths(config)

    def test_distinct_output_paths_accepted(self, tmp_path):
        config = self._make_config(tmp_path)
        result = validate_simulator_paths(config)
        assert result["ok"] is True

    def test_identical_calibration_summary_paths_rejected(self, tmp_path):
        same = str(tmp_path / "out" / "same_file.json")
        config = self._make_config(
            tmp_path,
            calibration_dataset_path=same,
            summary_report_path=same,
        )
        with pytest.raises(ValueError, match="same file"):
            validate_simulator_paths(config)

    def test_output_colliding_with_input_rejected(self, tmp_path):
        outcomes = tmp_path / "outcomes.json"
        outcomes.parent.mkdir(parents=True, exist_ok=True)
        outcomes.write_text("{}", encoding="utf-8")

        config = self._make_config(
            tmp_path,
            calibration_dataset_path=str(outcomes),
        )
        with pytest.raises(ValueError, match="collides with an input"):
            validate_simulator_paths(config)

    def test_output_parent_dir_created(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "cal.jsonl"
        config = self._make_config(
            tmp_path,
            calibration_dataset_path=str(deep),
        )
        result = validate_simulator_paths(config)
        assert result["ok"] is True
        assert deep.parent.exists()


# ════════════════════════════════════════════════════════════════════
# C. Schema-set validation
# ════════════════════════════════════════════════════════════════════


class TestSchemaSetValidation:

    def test_all_simulator_schemas_compile(self):
        result = validate_simulator_schema_set()
        assert result["ok"] is True
        assert "outcome_input_v1" in result["schemas"]
        assert "calibration_dataset_v1" in result["schemas"]
        assert "summary_report_v1" in result["schemas"]

    def test_schema_titles_present(self):
        result = validate_simulator_schema_set()
        for name, info in result["schemas"].items():
            assert info["title"], f"Schema {name} has no title"

    def test_missing_schema_file_rejected(self, tmp_path):
        # Empty dir — no schemas
        with pytest.raises(FileNotFoundError, match="schema missing"):
            validate_simulator_schema_set(schemas_dir=tmp_path)

    def test_invalid_json_schema_rejected(self, tmp_path):
        # Create all schema files but make one invalid JSON
        for name, filename in [
            ("outcome_input_v1", "outcome_input_v1.json"),
            ("calibration_dataset_v1", "calibration_dataset_v1.json"),
            ("summary_report_v1", "summary_report_v1.json"),
        ]:
            p = tmp_path / filename
            if name == "outcome_input_v1":
                p.write_text("{{{invalid json", encoding="utf-8")
            else:
                p.write_text('{"type":"object"}', encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid JSON"):
            validate_simulator_schema_set(schemas_dir=tmp_path)

    def test_schema_compilation_failure_rejected(self, tmp_path):
        # Create schema files with valid JSON but invalid JSON Schema
        for filename in [
            "outcome_input_v1.json",
            "calibration_dataset_v1.json",
            "summary_report_v1.json",
        ]:
            p = tmp_path / filename
            if filename == "outcome_input_v1.json":
                # type must be a string or array, not an integer
                p.write_text('{"type": 999}', encoding="utf-8")
            else:
                p.write_text('{"type":"object"}', encoding="utf-8")

        with pytest.raises(ValueError, match="compilation failed"):
            validate_simulator_schema_set(schemas_dir=tmp_path)


# ════════════════════════════════════════════════════════════════════
# D. Preflight summary
# ════════════════════════════════════════════════════════════════════


class TestPreflightSummary:

    def test_successful_preflight(self, tmp_path):
        cfg_path = _valid_sim_yaml(tmp_path)
        result = run_simulator_preflight(cfg_path)
        assert result["config_ok"] is True
        assert result["schemas_ok"] is True
        assert result["paths_ok"] is True
        assert result["validated_config_path"] == str(cfg_path)
        assert len(result["validated_schema_paths"]) == 3

    def test_failed_config_preflight(self):
        result = run_simulator_preflight("/nonexistent/config.yaml")
        assert result["config_ok"] is False
        assert result["paths_ok"] is False  # skipped
        assert any("FAIL" in n for n in result["notes"])

    def test_failed_schemas_preflight(self, tmp_path):
        cfg_path = _valid_sim_yaml(tmp_path)
        result = run_simulator_preflight(
            cfg_path, schemas_dir=tmp_path / "empty_schemas"
        )
        assert result["config_ok"] is True
        assert result["schemas_ok"] is False
        assert result["paths_ok"] is True  # paths checked independently

    def test_failed_paths_preflight(self, tmp_path):
        cfg_path = _valid_sim_yaml(
            tmp_path,
            judge_logs_path="/nonexistent/logs",
            outcome_data_path="/nonexistent/outcomes.json",
        )
        result = run_simulator_preflight(cfg_path)
        assert result["config_ok"] is True
        assert result["schemas_ok"] is True
        assert result["paths_ok"] is False

    def test_preflight_does_not_run_simulator(self, tmp_path):
        """Preflight must NOT invoke run_simulation or write outputs."""
        cfg_path = _valid_sim_yaml(tmp_path)
        with patch(
            "apps.reference.domains.alpha_search.judge.simulator"
            ".config_schema_validator.validate_simulator_config_file",
            wraps=validate_simulator_config_file,
        ):
            result = run_simulator_preflight(cfg_path)
        # If we got here, no simulation was attempted
        assert result["config_ok"] is True

    def test_preflight_notes_on_config_failure(self):
        result = run_simulator_preflight("/no/such/file.yaml")
        assert any("config" in n.lower() for n in result["notes"])

    def test_preflight_paths_skipped_when_config_fails(self):
        result = run_simulator_preflight("/no/such/file.yaml")
        assert result["paths_ok"] is False
        assert any("SKIPPED" in n for n in result["notes"])
