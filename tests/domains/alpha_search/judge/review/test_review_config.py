from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from apps.reference.domains.alpha_search.judge.review.config_schema_validator import (
    run_review_preflight,
    validate_review_config_file,
)


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_simulator_config(path: Path, *, judge_logs_path: str, outcome_data_path: str) -> None:
    _write_yaml(
        path,
        {
            "judge_simulator": {
                "enabled": True,
                "judge_logs_path": judge_logs_path,
                "outcome_data_path": outcome_data_path,
                "calibration_dataset_path": str(path.parent / "phase5_calibration.jsonl"),
                "summary_report_path": str(path.parent / "phase5_summary_report.json"),
                "fee_per_cycle_bps": 25.0,
                "slippage_pct": 0.1,
            }
        },
    )


def test_validate_review_config_file_accepts_valid_config(tmp_path: Path):
    verdict_path = tmp_path / "verdict_shadow.jsonl"
    verdict_path.write_text("", encoding="utf-8")
    outcome_path = tmp_path / "outcomes.json"
    outcome_path.write_text(
        '{"schema_version":"1","outcomes":[]}', encoding="utf-8")
    simulator_config_path = tmp_path / "judge_simulator.yaml"
    _write_simulator_config(
        simulator_config_path,
        judge_logs_path=str(verdict_path),
        outcome_data_path=str(outcome_path),
    )
    review_config_path = tmp_path / "judge_review.yaml"
    _write_yaml(
        review_config_path,
        {
            "judge_review": {
                "enabled": False,
                "judge_simulator_config_path": str(simulator_config_path),
                "output_dir": str(tmp_path / "artifacts" / "judge_review"),
                "segment_dimensions": ["symbol", "regime", "source_file"],
                "confidence_bucket_edges": [0.0, 0.25, 0.5, 0.75, 1.0],
            }
        },
    )

    config = validate_review_config_file(review_config_path)

    assert config.judge_simulator_config_path == str(simulator_config_path)
    assert config.segment_dimensions == ("symbol", "regime", "source_file")


def test_validate_review_config_file_rejects_duplicate_segment_dimensions(tmp_path: Path):
    review_config_path = tmp_path / "judge_review.yaml"
    _write_yaml(
        review_config_path,
        {
            "judge_review": {
                "enabled": False,
                "judge_simulator_config_path": str(tmp_path / "judge_simulator.yaml"),
                "output_dir": str(tmp_path / "artifacts" / "judge_review"),
                "segment_dimensions": ["symbol", "symbol"],
                "confidence_bucket_edges": [0.0, 0.5, 1.0],
            }
        },
    )

    with pytest.raises(ValueError, match="duplicates"):
        validate_review_config_file(review_config_path)


def test_run_review_preflight_fails_closed_on_missing_simulator_inputs(tmp_path: Path):
    simulator_config_path = tmp_path / "judge_simulator.yaml"
    _write_simulator_config(
        simulator_config_path,
        judge_logs_path=str(tmp_path / "missing_verdict_dir"),
        outcome_data_path=str(tmp_path / "missing_outcomes.json"),
    )
    review_config_path = tmp_path / "judge_review.yaml"
    _write_yaml(
        review_config_path,
        {
            "judge_review": {
                "enabled": False,
                "judge_simulator_config_path": str(simulator_config_path),
                "output_dir": str(tmp_path / "artifacts" / "judge_review"),
                "segment_dimensions": ["symbol", "source_file"],
                "confidence_bucket_edges": [0.0, 0.5, 1.0],
            }
        },
    )

    preflight = run_review_preflight(review_config_path)

    assert preflight["config_ok"] is True
    assert preflight["simulator_ok"] is True
    assert preflight["paths_ok"] is False
    assert any(
        "judge logs path" in note or "missing" in note for note in preflight["notes"])
