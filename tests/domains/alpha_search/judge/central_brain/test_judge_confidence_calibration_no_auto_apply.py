from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from apps.reference.domains.alpha_search.judge.central_brain.calibration import (
    build_calibration_proposal,
)

from tests.domains.alpha_search.judge.central_brain.test_judge_confidence_calibration_contract import (
    valid_row,
)


CALIBRATION_MODULE = Path("apps/reference/domains/alpha_search/judge/central_brain/calibration.py")
CLI_TOOL = Path("tools/judge/rolling_confidence_calibration.py")
FORBIDDEN_TEXT = (
    "execution_position",
    "OrderExecutor",
    "PLACE_ORDER",
    "CMD:OPEN",
    "CMD:CLOSE",
    "exchange_adapter",
    "binance",
    "judge_bridge",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_calibration_module_imports_no_execution_or_bridge_authority():
    text = _text(CALIBRATION_MODULE)
    for forbidden in FORBIDDEN_TEXT:
        assert forbidden not in text


def test_cli_imports_no_execution_or_order_surfaces():
    text = _text(CLI_TOOL)
    for forbidden in FORBIDDEN_TEXT:
        assert forbidden not in text


def test_proposal_always_no_auto_apply_and_no_promotion():
    proposal = build_calibration_proposal(
        [
            valid_row(row_id="a", decision_ts_ms=1000, judge_confidence=0.8),
            valid_row(row_id="b", decision_ts_ms=2000, judge_confidence=0.81),
        ],
        created_ts_ms=3000,
        band_step=0.10,
        cadence_days=4,
        min_rows=2,
        min_symbols=1,
    )
    dumped = proposal.model_dump(mode="json", by_alias=True)
    assert dumped["recommended_policy"]["auto_apply"] is False
    assert dumped["recommended_policy"]["proposal_only"] is True
    assert dumped["recommended_policy"]["human_review_required"] is True
    assert dumped["gates"]["promotion_allowed"] is False


def test_cli_writes_only_requested_outputs_under_temp_dir(tmp_path: Path):
    input_path = tmp_path / "rows.jsonl"
    output_json = tmp_path / "proposal.json"
    output_md = tmp_path / "proposal.md"
    rows = [
        valid_row(row_id="a", decision_ts_ms=1000, judge_confidence=0.85).model_dump(mode="json"),
        valid_row(row_id="b", decision_ts_ms=2000, judge_confidence=0.86).model_dump(mode="json"),
    ]
    input_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    before = {path.name for path in tmp_path.iterdir()}
    result = subprocess.run(
        [
            sys.executable,
            str(CLI_TOOL),
            "--input",
            str(input_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--band-step",
            "0.10",
            "--cadence-days",
            "4",
            "--min-rows",
            "2",
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
    after = {path.name for path in tmp_path.iterdir()}
    assert after - before == {"proposal.json", "proposal.md"}
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["recommended_policy"]["auto_apply"] is False
    assert payload["gates"]["promotion_allowed"] is False


def test_no_runtime_config_file_paths_in_calibration_code():
    combined = _text(CALIBRATION_MODULE) + "\n" + _text(CLI_TOOL)
    assert "config/aurora/domains" not in combined
    assert "config\\aurora\\domains" not in combined
