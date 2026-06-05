from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.domains.alpha_search.judge.central_brain.test_judge_shadow_calibration_row_contract import (
    valid_shadow_row,
)


RUNNER = Path("tools/judge/run_testnet_shadow_calibration_experiment.py")


def write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def run_experiment(tmp_path: Path, rows: list[dict], *, min_rows: int = 2):
    input_path = tmp_path / "shadow_rows.jsonl"
    output_dir = tmp_path / "out"
    write_rows(input_path, rows)
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--input-jsonl",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--band-step",
            "0.10",
            "--cadence-days",
            "4",
            "--min-rows",
            str(min_rows),
            "--min-symbols",
            "1",
            "--holdout-ratio",
            "0.0",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return output_dir, json.loads((output_dir / "proposal.json").read_text(encoding="utf-8"))


def row(row_id: str, confidence: float, net: float):
    return valid_shadow_row(
        row_id=row_id,
        verdict={
            "verdict_id": f"v-{row_id}",
            "verdict": "OPEN_LONG",
            "confidence": confidence,
            "authority_status": "shadow_only",
            "applied": False,
        },
        outcome={
            "outcome_status": "RESOLVED",
            "outcome_ts_ms": 2000,
            "horizon_sec": 300,
            "gross_pnl_usd": net,
            "net_pnl_usd": net,
            "fees_usd": None,
            "slippage_usd": None,
            "max_favorable_usd": None,
            "max_adverse_usd": None,
            "terminal_status": "closed",
        },
    ).model_dump(mode="json")


def test_runner_consumes_fixture_and_writes_outputs(tmp_path: Path):
    output_dir, proposal = run_experiment(tmp_path, [row("a", 0.85, 1.0), row("b", 0.86, 1.2)])
    assert (output_dir / "proposal.json").exists()
    assert (output_dir / "summary.md").exists()
    assert (output_dir / "diagnostics.json").exists()
    assert proposal["dataset_summary"]["total_rows"] == 2


def test_runner_preserves_no_promotion_policy(tmp_path: Path):
    _, proposal = run_experiment(tmp_path, [row("a", 0.85, 1.0), row("b", 0.86, 1.2)])
    assert proposal["gates"]["promotion_allowed"] is False
    assert proposal["recommended_policy"]["auto_apply"] is False
    assert proposal["recommended_policy"]["human_review_required"] is True


def test_low_power_dataset_does_not_promote(tmp_path: Path):
    _, proposal = run_experiment(tmp_path, [row("a", 0.85, 1.0)], min_rows=5)
    statuses = {band["status"] for band in proposal["confidence_bands"]["candidates"]}
    assert statuses == {"LOW_POWER"}
    assert proposal["gates"]["promotion_allowed"] is False


def test_positive_sufficient_fixture_produces_candidate_without_promotion(tmp_path: Path):
    _, proposal = run_experiment(tmp_path, [row("a", 0.85, 1.0), row("b", 0.86, 1.2)])
    statuses = {band["status"] for band in proposal["confidence_bands"]["candidates"]}
    assert "CANDIDATE" in statuses
    assert proposal["gates"]["promotion_allowed"] is False


def test_toxic_fixture_produces_toxic(tmp_path: Path):
    _, proposal = run_experiment(tmp_path, [row("a", 0.95, -1.0), row("b", 0.96, -1.2)])
    statuses = {band["status"] for band in proposal["confidence_bands"]["candidates"]}
    assert "TOXIC" in statuses


def test_summary_contains_required_sections(tmp_path: Path):
    output_dir, _ = run_experiment(tmp_path, [row("a", 0.85, 1.0), row("b", 0.86, 1.2)])
    summary = (output_dir / "summary.md").read_text(encoding="utf-8")
    assert "promotion_allowed: `False`" in summary
    assert "auto_apply: `False`" in summary
    assert "human_review_required: `True`" in summary


def test_no_config_files_written(tmp_path: Path):
    output_dir, _ = run_experiment(tmp_path, [row("a", 0.85, 1.0), row("b", 0.86, 1.2)])
    written = {path.name for path in output_dir.iterdir()}
    assert written == {"proposal.json", "summary.md", "diagnostics.json"}
