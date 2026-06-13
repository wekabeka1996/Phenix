#!/usr/bin/env python3
"""
Analyze Alpha Search Shadow Performance Metrics
================================================
Reads the summary.jsonl file from the latest backtest runtime session
and prints/saves a beautiful Markdown performance analysis report.
"""

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import math


def find_latest_session_dir() -> Path:
    base_dir = Path("logs") / "alpha_search_runtime"
    if not base_dir.exists():
        raise FileNotFoundError(f"Base logs directory does not exist: {base_dir}")

    sessions = [d for d in base_dir.iterdir() if d.is_dir()]
    if not sessions:
        raise FileNotFoundError(f"No session directories found under {base_dir}")

    # Session directories are named YYYYMMDD_HHMMSS
    return max(sessions, key=lambda d: d.name)


def format_pct(x: float) -> str:
    if math.isnan(x):
        return "n/a"
    return f"{100.0 * x:.2f}%"


def format_float(x: float, digits: int = 2) -> str:
    if math.isnan(x):
        return "n/a"
    if math.isinf(x):
        return "inf"
    return f"{x:.{digits}f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze shadow performance metrics.")
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Specific session directory name, e.g. 20260607_143910 (default: latest)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="reports/alpha_search_performance_report.md",
        help="Output markdown file path",
    )

    args = parser.parse_args()

    if args.session:
        session_dir = Path("logs") / "alpha_search_runtime" / args.session
    else:
        try:
            session_dir = find_latest_session_dir()
        except Exception as e:
            print(f"Error: {e}")
            return 1

    summary_file = session_dir / "aggregate" / "summary.jsonl"
    if not summary_file.exists():
        print(f"Error: summary file not found: {summary_file}")
        return 1

    print(f"Loading summaries from: {summary_file}")

    # Read the last line of summary.jsonl to get the final aggregate summary
    final_record = None
    with open(summary_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                final_record = json.loads(line)
            except json.JSONDecodeError:
                pass

    if not final_record:
        print(f"Error: No valid JSON records found in {summary_file}")
        return 1

    scenarios = final_record.get("scenarios", {})
    if not scenarios:
        print("Error: No scenario details in the summary.")
        return 1

    # Extract metrics
    perf_data = []
    for sid, sc in scenarios.items():
        shadow = sc.get("shadow_metrics", {})
        
        # Fall back to plugin stats if shadow metrics are zero/empty
        plugin_vtrader = {}
        providers = sc.get("plugin", {}).get("provider_stats", {})
        if providers:
            p_name = list(providers.keys())[0]
            plugin_vtrader = providers[p_name].get("virtual_trader", {})

        total_trades = shadow.get("total_trades", plugin_vtrader.get("trades_closed", 0))
        win_rate = shadow.get("win_rate", plugin_vtrader.get("win_rate", 0.0))
        pnl = shadow.get("cumulative_pnl", plugin_vtrader.get("total_pnl", 0.0))
        drawdown = shadow.get("max_drawdown", 0.0)
        sharpe = shadow.get("sharpe_ratio", 0.0)
        avg_pnl = shadow.get("avg_pnl_per_trade", 0.0)

        perf_data.append({
            "scenario_id": sid,
            "strategy_type": sc.get("strategy_type", "unknown"),
            "total_trades": total_trades,
            "wins": shadow.get("wins", plugin_vtrader.get("wins", 0)),
            "losses": shadow.get("losses", total_trades - shadow.get("wins", 0)),
            "win_rate": win_rate,
            "pnl": pnl,
            "max_drawdown": drawdown,
            "sharpe_ratio": sharpe,
            "avg_pnl": avg_pnl,
        })

    # Sort scenarios by PnL descending
    perf_data.sort(key=lambda x: x["pnl"], reverse=True)

    # Generate Markdown Report
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Alpha Search — Strategy Performance Analysis",
        "",
        f"- **Session Directory**: `{session_dir.name}`",
        f"- **Generated At**: {now_str}",
        f"- **Matrix ID**: `{final_record.get('matrix_id', 'unknown')}`",
        f"- **Total Snapshots**: {final_record.get('snapshots_dispatched', 0)}",
        "",
        "## Performance Leaderboard",
        "",
        "| Scenario ID | Strategy | Trades | Wins | Losses | Win Rate | Net PnL | Max Drawdown | Sharpe | Avg PnL/Trade |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]

    for p in perf_data:
        row = (
            f"| **{p['scenario_id']}** | {p['strategy_type']} | {p['total_trades']} | {p['wins']} | {p['losses']} | "
            f"{format_pct(p['win_rate'])} | **{format_float(p['pnl'])}** | {format_float(p['max_drawdown'])} | "
            f"{format_float(p['sharpe_ratio'])} | {format_float(p['avg_pnl'])} |"
        )
        lines.append(row)

    lines.append("")
    lines.append("## Strategy Insights")
    lines.append("")
    lines.append("### 1. Top Performing Strategy")
    if perf_data:
        top = perf_data[0]
        lines.append(
            f"The best performing scenario is **{top['scenario_id']}** ({top['strategy_type']}) with a Net PnL of **{top['pnl']}** "
            f"and a win rate of **{format_pct(top['win_rate'])}** over **{top['total_trades']}** trades. "
            f"Sharpe Ratio: **{format_float(top['sharpe_ratio'])}**, Max Drawdown: **{format_float(top['max_drawdown'])}**."
        )
    else:
        lines.append("No trading data available.")

    lines.append("")
    lines.append("### 2. Strategy Group Comparison")
    
    # Aggregate stats by strategy family
    group_stats = {}
    for p in perf_data:
        st = p["strategy_type"]
        g = group_stats.setdefault(st, {"pnl": 0.0, "trades": 0, "wins": 0, "count": 0})
        g["pnl"] += p["pnl"]
        g["trades"] += p["total_trades"]
        g["wins"] += p["wins"]
        g["count"] += 1

    lines.append("| Strategy Family | Count | Total Trades | Avg Win Rate | Total Net PnL | Avg PnL/Scenario |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
    for st, g in sorted(group_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
        avg_wr = g["wins"] / g["trades"] if g["trades"] > 0 else 0.0
        avg_pnl = g["pnl"] / g["count"] if g["count"] > 0 else 0.0
        lines.append(
            f"| {st} | {g['count']} | {g['trades']} | {format_pct(avg_wr)} | **{format_float(g['pnl'])}** | {format_float(avg_pnl)} |"
        )

    lines.append("")

    # Save to report file
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written to: {out_path}")

    # Output simple leaderboard to terminal
    print("\nLEADERBOARD")
    print("-" * 80)
    print(f"{'Scenario ID':<35} | {'Strategy':<15} | {'PnL':<10} | {'Win Rate':<10} | {'Sharpe':<8}")
    print("-" * 80)
    for p in perf_data[:10]:
        print(f"{p['scenario_id']:<35} | {p['strategy_type']:<15} | {p['pnl']:<10.2f} | {format_pct(p['win_rate']):<10} | {p['sharpe_ratio']:<8.2f}")
    print("-" * 80)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
