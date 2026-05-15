from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from tools.analysis.order_reconstruction_tp_sl_common import write_csv


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_trade_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = [row for row in rows if row.get("status") in {"win", "loss", "flat"}]
    net_values = [float(row["net_pnl_roi_pct"]) for row in resolved if row.get("net_pnl_roi_pct") != ""]
    wins = sum(1 for row in resolved if row.get("status") == "win")
    losses = sum(1 for row in resolved if row.get("status") == "loss")
    unresolved = sum(1 for row in rows if row.get("status") == "unresolved")
    gross_profit = sum(value for value in net_values if value > 0)
    gross_loss = abs(sum(value for value in net_values if value < 0))
    return {
        "trades": len(rows),
        "resolved_trades": len(resolved),
        "wins": wins,
        "losses": losses,
        "unresolved": unresolved,
        "win_rate": round(wins / len(resolved), 6) if resolved else 0.0,
        "avg_net_roi": round(mean(net_values), 8) if net_values else 0.0,
        "total_net_roi": round(sum(net_values), 8) if net_values else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 8) if gross_loss > 0 else "",
    }


def _breakdown(rows: list[dict[str, Any]], field_name: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(field_name) or "UNKNOWN"), []).append(row)
    payload: list[dict[str, Any]] = []
    for key, group_rows in sorted(grouped.items()):
        summary = summarize_trade_results(group_rows)
        summary[field_name] = key
        payload.append(summary)
    return payload


def _markdown_table(rows: list[dict[str, Any]], first_column: str) -> list[str]:
    if not rows:
        return ["| value | trades | wins | losses | unresolved | win_rate | avg_net_roi | total_net_roi | profit_factor |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    lines = [
        f"| {first_column} | trades | wins | losses | unresolved | win_rate | avg_net_roi | total_net_roi | profit_factor |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row[first_column]} | {row['trades']} | {row['wins']} | {row['losses']} | {row['unresolved']} | "
            f"{row['win_rate']} | {row['avg_net_roi']} | {row['total_net_roi']} | {row['profit_factor']} |"
        )
    return lines


def write_scenario_artifacts(
    scenario_root: Path,
    scenario_id: str,
    report_contract: str,
    trade_rows: list[dict[str, Any]],
    blocked_rows: list[dict[str, Any]],
    request_join_audit_rows: list[dict[str, Any]],
    baseline_summary: dict[str, Any] | None,
    assumptions: list[str],
    unknowns: list[str],
) -> dict[str, Any]:
    scenario_root.mkdir(parents=True, exist_ok=True)
    trade_headers = list(trade_rows[0].keys()) if trade_rows else [
        "scenario_id",
        "entry_id",
        "symbol",
        "side",
        "regime_at_entry",
        "entry_ts_ms",
        "entry_price",
        "exit_reason",
        "exit_source",
        "support_quality",
        "tp_price",
        "sl_price",
        "exit_ts_ms",
        "exit_price",
        "gross_pnl_roi_pct",
        "fee_roi_pct",
        "net_pnl_roi_pct",
        "status",
    ]
    blocked_headers = list(blocked_rows[0].keys()) if blocked_rows else [
        "scenario_id",
        "entry_id",
        "symbol",
        "side",
        "gate_id",
        "allowed",
        "reason",
        "detail",
        "support_quality",
    ]
    audit_headers = list(request_join_audit_rows[0].keys()) if request_join_audit_rows else [
        "entry_id",
        "symbol",
        "join_method",
        "join_quality",
        "join_delta_ms",
        "request_id",
        "request_ts_ms",
        "request_event_type",
        "trace_id",
        "source_line",
    ]
    write_csv(scenario_root / "trade_results.csv", trade_headers, trade_rows)
    if blocked_rows:
        write_csv(scenario_root / "blocked_entries.csv", blocked_headers, blocked_rows)
    if request_join_audit_rows:
        write_csv(scenario_root / "request_join_audit.csv", audit_headers, request_join_audit_rows)

    summary = summarize_trade_results(trade_rows)
    summary["scenario_id"] = scenario_id
    summary["blocked_entries"] = len(blocked_rows)
    summary["report_contract"] = report_contract
    summary["breakdown_by_symbol"] = _breakdown(trade_rows, "symbol")
    summary["breakdown_by_regime"] = _breakdown(trade_rows, "regime_at_entry")
    summary["breakdown_by_side"] = _breakdown(trade_rows, "side")
    summary["breakdown_by_exit_reason"] = _breakdown(trade_rows, "exit_reason")
    if baseline_summary is not None:
        summary["delta_vs_tp_sl_only"] = {
            "trades": summary["trades"] - int(baseline_summary.get("trades", 0)),
            "wins": summary["wins"] - int(baseline_summary.get("wins", 0)),
            "losses": summary["losses"] - int(baseline_summary.get("losses", 0)),
            "unresolved": summary["unresolved"] - int(baseline_summary.get("unresolved", 0)),
            "win_rate": round(summary["win_rate"] - float(baseline_summary.get("win_rate", 0.0)), 6),
            "avg_net_roi": round(summary["avg_net_roi"] - float(baseline_summary.get("avg_net_roi", 0.0)), 8),
            "total_net_roi": round(summary["total_net_roi"] - float(baseline_summary.get("total_net_roi", 0.0)), 8),
        }
    else:
        summary["delta_vs_tp_sl_only"] = None
    write_json(scenario_root / "scenario_summary.json", summary)

    lines = [
        f"# Scenario Report: {scenario_id}",
        "",
        f"Verdict: {'COMPLETE' if summary['trades'] or summary['blocked_entries'] else 'EMPTY'}",
        "",
        "## FACTS",
        f"- Scenario contract: {report_contract}",
        f"- Trades evaluated after entry filtering: {summary['trades']}",
        f"- Blocked entries by scenario filters: {summary['blocked_entries']}",
        f"- Wins: {summary['wins']}",
        f"- Losses: {summary['losses']}",
        f"- Unresolved: {summary['unresolved']}",
        f"- Win rate (resolved trades only): {summary['win_rate']}",
        f"- Avg net ROI: {summary['avg_net_roi']}",
        f"- Total net ROI: {summary['total_net_roi']}",
        f"- Profit factor: {summary['profit_factor']}",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| trades | {summary['trades']} |",
        f"| wins | {summary['wins']} |",
        f"| losses | {summary['losses']} |",
        f"| unresolved | {summary['unresolved']} |",
        f"| win_rate | {summary['win_rate']} |",
        f"| avg_net_roi | {summary['avg_net_roi']} |",
        f"| total_net_roi | {summary['total_net_roi']} |",
        f"| profit_factor | {summary['profit_factor']} |",
        "",
        "## Breakdown By Symbol",
        *_markdown_table(summary["breakdown_by_symbol"], "symbol"),
        "",
        "## Breakdown By Regime",
        *_markdown_table(summary["breakdown_by_regime"], "regime_at_entry"),
        "",
        "## Breakdown By Side",
        *_markdown_table(summary["breakdown_by_side"], "side"),
        "",
        "## Breakdown By Exit Reason",
        *_markdown_table(summary["breakdown_by_exit_reason"], "exit_reason"),
        "",
        "## INFERENCES",
        f"- Delta vs tp_sl_only: {json.dumps(summary['delta_vs_tp_sl_only'], ensure_ascii=False)}",
        f"- Entry-filter pressure is visible through blocked_entries={summary['blocked_entries']}.",
        "",
        "## ASSUMPTIONS",
    ]
    for item in assumptions:
        lines.append(f"- {item}")
    lines.extend(["", "## UNKNOWNS"])
    if unknowns:
        for item in unknowns:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    (scenario_root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
