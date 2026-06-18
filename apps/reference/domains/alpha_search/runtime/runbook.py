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

    Returns dict with best/worst by cost-aware net PnL when trades are available.
    """
    results: Dict[str, Dict[str, Any]] = {}

    scenario_dirs = sorted([
        d for d in session_dir.iterdir()
        if d.is_dir() and d.name != "aggregate" and d.name.startswith("S")
    ])

    for sdir in scenario_dirs:
        sid = sdir.name
        scores_path = sdir / "scores.jsonl"
        trades_path = sdir / "trades.jsonl"

        total_score = 0.0
        count = 0
        if scores_path.exists():
            with open(scores_path, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        total_score += record.get("score", 0.0)
                        count += 1
                    except json.JSONDecodeError:
                        continue

        trades = _read_jsonl(trades_path)
        economics = [_trade_economics(t) for t in trades]
        raw_pnl = sum(e["raw_pnl"] for e in economics)
        net_pnl_after_cost = sum(e["net_pnl_after_cost"] for e in economics)
        total_cost = sum(e["total_cost"] for e in economics)
        cost_status = (
            "COST_AWARE" if economics and all(e["cost_status"] == "COST_AWARE" for e in economics)
            else "LEGACY_RAW_ONLY" if economics
            else "NO_TRADES"
        )

        if count > 0 or trades:
            results[sid] = {
                "total_scores": count,
                "avg_score": round(total_score / count, 6) if count > 0 else 0.0,
                "strategy_type": _read_strategy_type(sdir),
                "total_trades": len(trades),
                "raw_pnl_diagnostic": round(raw_pnl, 4),
                "total_cost": round(total_cost, 4),
                "net_pnl_after_cost": round(net_pnl_after_cost, 4),
                "cost_status": cost_status,
            }

    if not results:
        return {"message": "No scenario data found"}

    ranked = {
        sid: row for sid, row in results.items()
        if row.get("cost_status") == "COST_AWARE"
    }
    if ranked:
        best_sid = max(ranked, key=lambda k: ranked[k]["net_pnl_after_cost"])
        worst_sid = min(ranked, key=lambda k: ranked[k]["net_pnl_after_cost"])
        ranking_metric = "net_pnl_after_cost"
    else:
        best_sid = None
        worst_sid = None
        ranking_metric = "NO_COST_AWARE_TRADES"

    return {
        "scenarios": results,
        "ranking_metric": ranking_metric,
        "best": {"scenario_id": best_sid, **results[best_sid]} if best_sid else None,
        "worst": {"scenario_id": worst_sid, **results[worst_sid]} if worst_sid else None,
    }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _trade_economics(trade: Dict[str, Any]) -> Dict[str, Any]:
    raw_pnl = _safe_float(trade.get("raw_pnl", trade.get("pnl", 0.0)))
    if "net_pnl_after_cost" not in trade:
        return {
            "raw_pnl": raw_pnl,
            "total_cost": 0.0,
            "net_pnl_after_cost": raw_pnl,
            "cost_status": "LEGACY_RAW_ONLY",
        }
    fee_cost = _safe_float(trade.get("fee_cost", trade.get("fees", 0.0)))
    slippage_cost = _safe_float(trade.get("slippage_cost", trade.get("slippage", 0.0)))
    total_cost = _safe_float(trade.get("total_cost", fee_cost + slippage_cost))
    return {
        "raw_pnl": raw_pnl,
        "total_cost": total_cost,
        "net_pnl_after_cost": _safe_float(trade.get("net_pnl_after_cost")),
        "cost_status": "COST_AWARE",
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
