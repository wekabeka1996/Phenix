"""
Runbook Utilities
=================

Operational helpers for alpha search standalone domain:
- Session report generation (markdown summary)
- Cross-scenario comparison
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG = logging.getLogger(__name__)


def generate_session_report(session_dir: Path) -> str:
    """
    Generate a markdown report summarizing all scenarios in a session.

    Reads from:
    - <session_dir>/aggregate/summary.jsonl (latest entry)
    - <session_dir>/<scenario_id>/config_effective.yaml
    - <session_dir>/<scenario_id>/scores.jsonl (line count)

    Returns markdown string.
    """
    report_lines = [
        f"# Alpha Search Session Report",
        f"**Session:** `{session_dir.name}`",
        f"**Generated:** {datetime.now().isoformat()}",
        "",
        "## Scenario Summary",
        "",
        "| Scenario | Strategy | Scores | Status |",
        "|----------|----------|--------|--------|",
    ]

    # Find scenario dirs
    scenario_dirs = sorted([
        d for d in session_dir.iterdir()
        if d.is_dir() and d.name != "aggregate" and d.name.startswith("S")
    ])

    for sdir in scenario_dirs:
        sid = sdir.name
        strategy = _read_strategy_type(sdir)
        score_count = _count_jsonl_lines(sdir / "scores.jsonl")
        status = "OK" if score_count > 0 else "EMPTY"

        report_lines.append(
            f"| {sid} | {strategy} | {score_count} | {status} |"
        )

    report_lines.extend([
        "",
        "## Aggregate Stats",
        "",
    ])

    # Read latest summary
    summary_path = session_dir / "aggregate" / "summary.jsonl"
    if summary_path.exists():
        try:
            last_line = ""
            with open(summary_path, "r") as f:
                for line in f:
                    last_line = line
            if last_line:
                summary = json.loads(last_line)
                scenarios = summary.get("scenarios", {})
                for sid, data in scenarios.items():
                    plugin = data.get("plugin", {})
                    report_lines.append(f"### {sid}")
                    report_lines.append(
                        f"- Processed: {data.get('snapshots_processed', 'N/A')}")
                    report_lines.append(
                        f"- Results: {data.get('total_results', 'N/A')}")
                    report_lines.append(
                        f"- Failed: {data.get('snapshots_failed', 'N/A')}")
                    report_lines.append("")
        except Exception as e:
            report_lines.append(f"*Error reading summary: {e}*")

    return "\n".join(report_lines)


def compare_scenarios(session_dir: Path) -> Dict[str, Any]:
    """
    Cross-scenario performance comparison.

    Returns dict with best/worst by PnL, Sharpe, win_rate across all scenarios.
    """
    results: Dict[str, Dict[str, Any]] = {}

    scenario_dirs = sorted([
        d for d in session_dir.iterdir()
        if d.is_dir() and d.name != "aggregate" and d.name.startswith("S")
    ])

    for sdir in scenario_dirs:
        sid = sdir.name
        scores_path = sdir / "scores.jsonl"
        if not scores_path.exists():
            continue

        # Aggregate scores
        total_score = 0.0
        count = 0
        try:
            with open(scores_path, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        total_score += record.get("score", 0.0)
                        count += 1
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

        if count > 0:
            results[sid] = {
                "total_scores": count,
                "avg_score": round(total_score / count, 6),
                "strategy_type": _read_strategy_type(sdir),
            }

    if not results:
        return {"message": "No scenario data found"}

    # Find best/worst
    best_sid = max(results, key=lambda k: results[k]["avg_score"])
    worst_sid = min(results, key=lambda k: results[k]["avg_score"])

    return {
        "scenarios": results,
        "best": {"scenario_id": best_sid, **results[best_sid]},
        "worst": {"scenario_id": worst_sid, **results[worst_sid]},
    }


def _read_strategy_type(scenario_dir: Path) -> str:
    """Read strategy type from effective config."""
    import yaml
    config_path = scenario_dir / "config_effective.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("strategy_type", cfg.get("scenario_id", "unknown"))
        except Exception:
            pass
    return "unknown"


def _count_jsonl_lines(path: Path) -> int:
    """Count lines in a JSONL file."""
    if not path.exists():
        return 0
    count = 0
    with open(path, "r") as f:
        for _ in f:
            count += 1
    return count
