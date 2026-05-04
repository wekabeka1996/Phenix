"""Tests for Phase 5 Package 5F — CLI harness.

Validates config loading, run orchestration, exit codes, and output
correctness.  Does NOT import from or modify any live runtime module.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from apps.reference.domains.alpha_search.judge.contracts import JudgeVerdict
from apps.reference.domains.alpha_search.judge.simulator.cli import (
    EXIT_BAD_CONFIG,
    EXIT_MISSING_INPUT,
    EXIT_SIMULATION_FAILURE,
    EXIT_SUCCESS,
    EXIT_WRITE_FAILURE,
    load_simulator_config,
    main,
    run_from_config,
)
from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    SimulatorConfig,
)


# ── helpers ───────────────────────────────────────────────────────────

def _write_yaml(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh)
    return path


def _minimal_config_dict() -> dict:
    return {
        "judge_simulator": {
            "enabled": True,
            "judge_logs_path": "logs/judge_experts",
            "outcome_data_path": "data/simulator/outcomes.json",
            "calibration_dataset_path": "artifacts/phase5_calibration.jsonl",
            "summary_report_path": "artifacts/phase5_summary_report.json",
            "fee_per_cycle_bps": 25.0,
            "slippage_pct": 0.1,
        }
    }


def _make_verdict(
    *,
    verdict_id: str = "v-1",
    strategy_id: str = "aurora",
    symbol: str = "BTCUSDT",
    tf_sec: int = 300,
    bar_close_ts: int = 1712000000000,
    entry_verdict: str = "OPEN_LONG",
    confidence: float = 0.8,
) -> JudgeVerdict:
    suppression_reason = None
    if entry_verdict == "SUPPRESS":
        suppression_reason = "test-suppressed"
    return JudgeVerdict(
        verdict_id=verdict_id,
        envelope_id=f"env-{verdict_id}",
        chamber_id=f"ch-{verdict_id}",
        symbol=symbol,
        tf_sec=tf_sec,
        ts_ms=bar_close_ts,
        verdict_scope="ENTRY",
        entry_verdict=entry_verdict,
        suppression_reason=suppression_reason,
        confidence=confidence,
        reasoning=["test"],
        dissent_noted=False,
        authority_mode="shadow",
        applied=False,
        strategy_id=strategy_id,
    )


def _write_verdict_jsonl(path: Path, verdicts: list[JudgeVerdict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for v in verdicts:
            fh.write(v.model_dump_json() + "\n")
    return path


def _write_outcome_json(path: Path, outcomes: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": "1", "outcomes": outcomes}, fh)
    return path


def _make_outcome(
    strategy_id: str = "aurora",
    symbol: str = "BTCUSDT",
    tf_sec: int = 300,
    bar_close_ts: int = 1712000000000,
    matched_trade: bool = True,
    entry_price: float = 60000.0,
    exit_price: float = 60300.0,
) -> dict:
    d: dict = {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": bar_close_ts,
        "matched_trade": matched_trade,
    }
    if matched_trade:
        d["entry_price"] = entry_price
        d["exit_price"] = exit_price
        d["exit_ts_ms"] = bar_close_ts + 5000
    return d


def _write_jsonl(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )


# ══════════════════════════════════════════════════════════════════════
# A. Config Loading
# ══════════════════════════════════════════════════════════════════════

class TestLoadSimulatorConfig:

    def test_valid_config_loads(self, tmp_path: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "sim.yaml", _minimal_config_dict())
        config = load_simulator_config(cfg_path)
        assert isinstance(config, SimulatorConfig)
        assert config.enabled is True
        assert config.fee_per_cycle_bps == 25.0
        assert config.slippage_pct == 0.1
        assert config.judge_logs_path == "logs/judge_experts"

    def test_malformed_yaml_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(":::not valid yaml:::", encoding="utf-8")
        with pytest.raises((ValueError, yaml.YAMLError)):
            load_simulator_config(bad)

    def test_missing_judge_simulator_key(self, tmp_path: Path) -> None:
        cfg_path = _write_yaml(tmp_path / "sim.yaml", {"other": {}})
        with pytest.raises(ValueError, match="judge_simulator"):
            load_simulator_config(cfg_path)

    def test_missing_required_field_rejected(self, tmp_path: Path) -> None:
        data = _minimal_config_dict()
        del data["judge_simulator"]["judge_logs_path"]
        cfg_path = _write_yaml(tmp_path / "sim.yaml", data)
        with pytest.raises(Exception):
            load_simulator_config(cfg_path)

    def test_invalid_path_value_rejected(self, tmp_path: Path) -> None:
        data = _minimal_config_dict()
        data["judge_simulator"]["judge_logs_path"] = ""
        cfg_path = _write_yaml(tmp_path / "sim.yaml", data)
        with pytest.raises(Exception):
            load_simulator_config(cfg_path)

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_simulator_config(tmp_path / "nonexistent.yaml")

    def test_extra_fields_rejected(self, tmp_path: Path) -> None:
        data = _minimal_config_dict()
        data["judge_simulator"]["bogus_field"] = 42
        cfg_path = _write_yaml(tmp_path / "sim.yaml", data)
        with pytest.raises(Exception):
            load_simulator_config(cfg_path)

    def test_negative_fee_rejected(self, tmp_path: Path) -> None:
        data = _minimal_config_dict()
        data["judge_simulator"]["fee_per_cycle_bps"] = -1.0
        cfg_path = _write_yaml(tmp_path / "sim.yaml", data)
        with pytest.raises(Exception):
            load_simulator_config(cfg_path)

    def test_non_mapping_judge_simulator_rejected(self, tmp_path: Path) -> None:
        data = {"judge_simulator": "not_a_mapping"}
        cfg_path = _write_yaml(tmp_path / "sim.yaml", data)
        with pytest.raises(ValueError, match="mapping"):
            load_simulator_config(cfg_path)


# ══════════════════════════════════════════════════════════════════════
# B. CLI Run Path
# ══════════════════════════════════════════════════════════════════════

def _build_sim_env(tmp_path: Path) -> dict:
    """Build a minimal valid simulation environment under tmp_path."""
    logs_dir = tmp_path / "logs" / "judge_experts"
    logs_dir.mkdir(parents=True, exist_ok=True)

    outcomes_path = tmp_path / "data" / "outcomes.json"
    cal_path = tmp_path / "artifacts" / "phase5_calibration.jsonl"
    summary_path = tmp_path / "artifacts" / "phase5_summary_report.json"

    verdict = _make_verdict(verdict_id="v-1")
    outcome = _make_outcome()

    _write_verdict_jsonl(logs_dir / "verdict_batch.jsonl", [verdict])
    _write_outcome_json(outcomes_path, [outcome])

    config_data = {
        "judge_simulator": {
            "enabled": True,
            "judge_logs_path": str(logs_dir),
            "outcome_data_path": str(outcomes_path),
            "calibration_dataset_path": str(cal_path),
            "summary_report_path": str(summary_path),
            "fee_per_cycle_bps": 25.0,
            "slippage_pct": 0.1,
        }
    }
    cfg_path = _write_yaml(tmp_path / "sim.yaml", config_data)

    return {
        "cfg_path": cfg_path,
        "cal_path": cal_path,
        "summary_path": summary_path,
        "tmp_path": tmp_path,
    }


class TestCLIRunPath:

    @pytest.fixture()
    def sim_env(self, tmp_path: Path) -> dict:
        return _build_sim_env(tmp_path)

    def test_main_returns_zero_on_success(self, sim_env: dict) -> None:
        exit_code = main(["--config", str(sim_env["cfg_path"])])
        assert exit_code == EXIT_SUCCESS

    def test_calibration_dataset_written(self, sim_env: dict) -> None:
        main(["--config", str(sim_env["cfg_path"])])
        cal = Path(sim_env["cal_path"])
        assert cal.exists()
        lines = cal.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        for line in lines:
            record = json.loads(line)
            assert "strategy_id" in record
            assert "cohort" in record

    def test_summary_report_written(self, sim_env: dict) -> None:
        main(["--config", str(sim_env["cfg_path"])])
        summary = Path(sim_env["summary_path"])
        assert summary.exists()
        report = json.loads(summary.read_text(encoding="utf-8"))
        assert report["schema_version"] == "1"
        assert "input_counts" in report
        assert "economics" in report

    def test_run_from_config_returns_result(self, sim_env: dict) -> None:
        config = load_simulator_config(sim_env["cfg_path"])
        result = run_from_config(config)
        assert result.total_verdict_records_loaded >= 1
        assert result.total_outcome_records_loaded >= 1

    def test_calibration_is_valid_jsonl(self, sim_env: dict) -> None:
        main(["--config", str(sim_env["cfg_path"])])
        cal = Path(sim_env["cal_path"])
        for line in cal.read_text(encoding="utf-8").strip().splitlines():
            record = json.loads(line)
            assert record.get("schema_version") == "1"

    def test_summary_has_all_required_keys(self, sim_env: dict) -> None:
        main(["--config", str(sim_env["cfg_path"])])
        summary = Path(sim_env["summary_path"])
        report = json.loads(summary.read_text(encoding="utf-8"))
        for key in [
            "schema_version",
            "generated_at_ms",
            "input_counts",
            "match_stats",
            "economics",
            "disagreement_stats",
            "expert_accuracy_summary",
            "cohort_stats",
            "policy_readiness_notes",
        ]:
            assert key in report, f"Missing key: {key}"


# ══════════════════════════════════════════════════════════════════════
# C. Failure Behavior
# ══════════════════════════════════════════════════════════════════════

class TestCLIFailureBehavior:

    def test_missing_config_file_returns_bad_config(self) -> None:
        exit_code = main(["--config", "/nonexistent/path/sim.yaml"])
        assert exit_code == EXIT_BAD_CONFIG

    def test_malformed_config_returns_bad_config(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("judge_simulator: not_a_mapping", encoding="utf-8")
        exit_code = main(["--config", str(bad)])
        assert exit_code == EXIT_BAD_CONFIG

    def test_missing_input_returns_missing_input(self, tmp_path: Path) -> None:
        config_data = {
            "judge_simulator": {
                "enabled": True,
                "judge_logs_path": str(tmp_path / "no_such_dir"),
                "outcome_data_path": str(tmp_path / "no_such.json"),
                "calibration_dataset_path": str(tmp_path / "cal.jsonl"),
                "summary_report_path": str(tmp_path / "sum.json"),
            }
        }
        cfg_path = _write_yaml(tmp_path / "sim.yaml", config_data)
        exit_code = main(["--config", str(cfg_path)])
        assert exit_code == EXIT_MISSING_INPUT

    def test_invalid_outcome_returns_simulation_failure(
        self, tmp_path: Path
    ) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        _write_verdict_jsonl(
            logs_dir / "verdict_batch.jsonl",
            [_make_verdict(verdict_id="v-1")],
        )
        outcome_path = tmp_path / "outcomes.json"
        outcome_path.write_text('{"bad": true}', encoding="utf-8")

        config_data = {
            "judge_simulator": {
                "enabled": True,
                "judge_logs_path": str(logs_dir),
                "outcome_data_path": str(outcome_path),
                "calibration_dataset_path": str(tmp_path / "cal.jsonl"),
                "summary_report_path": str(tmp_path / "sum.json"),
            }
        }
        cfg_path = _write_yaml(tmp_path / "sim.yaml", config_data)
        exit_code = main(["--config", str(cfg_path)])
        assert exit_code == EXIT_SIMULATION_FAILURE

    def test_calibration_writer_failure_surfaced(
        self, tmp_path: Path
    ) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        _write_verdict_jsonl(
            logs_dir / "verdict_batch.jsonl",
            [_make_verdict(verdict_id="v-1")],
        )
        outcome_path = tmp_path / "outcomes.json"
        _write_outcome_json(outcome_path, [_make_outcome()])

        cal_dir = tmp_path / "cal_is_dir.jsonl"
        cal_dir.mkdir(parents=True, exist_ok=True)

        config_data = {
            "judge_simulator": {
                "enabled": True,
                "judge_logs_path": str(logs_dir),
                "outcome_data_path": str(outcome_path),
                "calibration_dataset_path": str(cal_dir),
                "summary_report_path": str(tmp_path / "sum.json"),
            }
        }
        cfg_path = _write_yaml(tmp_path / "sim.yaml", config_data)
        exit_code = main(["--config", str(cfg_path)])
        assert exit_code == EXIT_SIMULATION_FAILURE

    def test_summary_writer_failure_surfaced(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        _write_verdict_jsonl(
            logs_dir / "verdict_batch.jsonl",
            [_make_verdict(verdict_id="v-1")],
        )
        outcome_path = tmp_path / "outcomes.json"
        _write_outcome_json(outcome_path, [_make_outcome()])

        summary_dir = tmp_path / "sum_is_dir.json"
        summary_dir.mkdir(parents=True, exist_ok=True)

        config_data = {
            "judge_simulator": {
                "enabled": True,
                "judge_logs_path": str(logs_dir),
                "outcome_data_path": str(outcome_path),
                "calibration_dataset_path": str(tmp_path / "cal.jsonl"),
                "summary_report_path": str(summary_dir),
            }
        }
        cfg_path = _write_yaml(tmp_path / "sim.yaml", config_data)
        exit_code = main(["--config", str(cfg_path)])
        assert exit_code == EXIT_SIMULATION_FAILURE


# ══════════════════════════════════════════════════════════════════════
# D. Determinism & Output Correctness
# ══════════════════════════════════════════════════════════════════════

class TestOutputCorrectness:

    @pytest.fixture()
    def sim_env(self, tmp_path: Path) -> dict:
        return _build_sim_env(tmp_path)

    def test_deterministic_double_run(self, sim_env: dict) -> None:
        config = load_simulator_config(sim_env["cfg_path"])
        run_from_config(config)
        summary1 = json.loads(
            Path(sim_env["summary_path"]).read_text(encoding="utf-8")
        )
        # Remove calibration (create-only policy) for second run
        Path(sim_env["cal_path"]).unlink(missing_ok=True)
        run_from_config(config)
        summary2 = json.loads(
            Path(sim_env["summary_path"]).read_text(encoding="utf-8")
        )
        assert summary1 == summary2

    def test_calibration_records_have_correct_cohorts(
        self, sim_env: dict
    ) -> None:
        main(["--config", str(sim_env["cfg_path"])])
        cal = Path(sim_env["cal_path"])
        valid_cohorts = {
            "CORRECT_ENTRY",
            "INCORRECT_ENTRY",
            "CORRECT_ABSTAIN",
            "MISSED_OPPORTUNITY",
            "INCONCLUSIVE",
        }
        for line in cal.read_text(encoding="utf-8").strip().splitlines():
            record = json.loads(line)
            assert record["cohort"] in valid_cohorts


# ══════════════════════════════════════════════════════════════════════
# E. Exit code constants
# ══════════════════════════════════════════════════════════════════════

class TestExitCodes:

    def test_exit_codes_are_distinct(self) -> None:
        codes = [
            EXIT_SUCCESS,
            EXIT_BAD_CONFIG,
            EXIT_MISSING_INPUT,
            EXIT_SIMULATION_FAILURE,
            EXIT_WRITE_FAILURE,
        ]
        assert len(codes) == len(set(codes))

    def test_success_is_zero(self) -> None:
        assert EXIT_SUCCESS == 0

    def test_failure_codes_are_nonzero(self) -> None:
        for code in [
            EXIT_BAD_CONFIG,
            EXIT_MISSING_INPUT,
            EXIT_SIMULATION_FAILURE,
            EXIT_WRITE_FAILURE,
        ]:
            assert code != 0
