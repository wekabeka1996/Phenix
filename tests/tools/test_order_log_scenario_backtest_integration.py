from __future__ import annotations

import json
from pathlib import Path

from tools.order_log_scenario_backtest.cli import run_backtest

from .test_order_log_scenario_backtest_core import _build_runtime


def test_run_backtest_all_scenarios(tmp_path: Path) -> None:
    workspace_root, runtime_root, report_root, _ = _build_runtime(tmp_path)
    manifest = run_backtest(
        workspace_root=workspace_root,
        runtime_root=runtime_root,
        report_root=report_root,
        recorder_root=workspace_root / "data" / "recorder",
        extra_recorder_roots=[],
        scenarios="all",
        strict=True,
    )
    assert manifest["status"] == "complete"
    assert manifest["canonical_entries"] == 3
    assert set(manifest["scenario_summaries"]) == {
        "tp_sl_only",
        "nrr026_only",
        "nrr027_only",
        "nrr028_only",
        "nrr029_only",
        "nrr030_only",
        "nrr027_030_no_regime_flip",
        "sidecar_only",
    }
    baseline = manifest["scenario_summaries"]["tp_sl_only"]
    assert baseline["trades"] == 3
    assert baseline["wins"] == 2
    assert baseline["losses"] == 1
    assert baseline["unresolved"] == 0
    sidecar = manifest["scenario_summaries"]["sidecar_only"]
    assert sidecar["trades"] == 3
    assert sidecar["unresolved"] == 1
    assert (report_root / "tp_sl_only" / "report.md").exists()
    assert (report_root / "sidecar_only" / "request_join_audit.csv").exists()
    scenario_summary = json.loads((report_root / "nrr027_only" / "scenario_summary.json").read_text(encoding="utf-8"))
    assert scenario_summary["blocked_entries"] == 2


def test_run_backtest_fails_closed_on_missing_1m_coverage(tmp_path: Path) -> None:
    workspace_root, runtime_root, report_root, _ = _build_runtime(tmp_path)
    (workspace_root / "data" / "recorder" / "BTCUSDT_60.csv").unlink()
    manifest = run_backtest(
        workspace_root=workspace_root,
        runtime_root=runtime_root,
        report_root=report_root,
        recorder_root=workspace_root / "data" / "recorder",
        extra_recorder_roots=[],
        scenarios="tp_sl_only",
        strict=True,
    )
    assert manifest["status"] == "failed_strict_candle_coverage"
    assert (report_root / "required_1m_candle_windows.csv").exists()
