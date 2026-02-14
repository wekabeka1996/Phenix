#!/usr/bin/env python3
"""
Quick backtest log stats for Aurora.

Reads:
  - logs/backtests/order_log_*.jsonl
  - reports/backtests/backtest_*.json (auto-matched by artifacts.order_log_jsonl)

Prints:
  - how many orders were opened/placed/rejected/cancelled
  - top reject and cancel reasons
  - close reasons for trades
  - profit/loss and win rate
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs" / "backtests"
REPORTS_DIR = ROOT / "reports" / "backtests"


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _list_order_logs() -> list[Path]:
    files = sorted(LOGS_DIR.glob("order_log_*.jsonl"), key=lambda p: p.stat().st_mtime)
    return files


def _pick_order_log(path_arg: Optional[str]) -> Path:
    if path_arg:
        p = Path(path_arg)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            raise FileNotFoundError(f"Order log not found: {p}")
        return p

    files = sorted(LOGS_DIR.glob("order_log_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No order logs found in {LOGS_DIR}")
    return files[0]


def _find_report_for_order_log(order_log: Path, report_arg: Optional[str]) -> Optional[Path]:
    if report_arg:
        p = Path(report_arg)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            raise FileNotFoundError(f"Report not found: {p}")
        return p

    report_files = sorted(REPORTS_DIR.glob("backtest_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    target_name = order_log.name
    for rp in report_files:
        try:
            with rp.open("r", encoding="utf-8") as f:
                data = json.load(f)
            artifacts = data.get("artifacts", {}) if isinstance(data, dict) else {}
            order_ref = artifacts.get("order_log_jsonl")
            if isinstance(order_ref, str) and Path(order_ref).name == target_name:
                return rp
        except Exception:
            continue
    return None


def _summarize_order_log(order_log: Path) -> dict[str, Any]:
    event_counts: Counter[str] = Counter()
    reject_reasons: Counter[str] = Counter()
    cancel_reasons: Counter[str] = Counter()
    proposed_intents = 0
    strategy_intents = 0
    placed_orders = 0

    with order_log.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            event = str(row.get("event_type", "")).strip()
            if not event:
                continue
            event_counts[event] += 1

            if event == "ORDER_INTENT":
                meta = row.get("metadata", {})
                source = str(row.get("source_fsm", ""))
                if isinstance(meta, dict) and bool(meta.get("intent_proposed")):
                    proposed_intents += 1
                if source == "DecisionMaking":
                    strategy_intents += 1

            elif event == "ORDER_PLACED":
                placed_orders += 1

            elif event == "ORDER_REJECTED":
                nrr = str(row.get("nrr_code", "")).strip()
                why = str(row.get("why", "")).strip()
                key = f"{nrr} | {why}" if nrr else (why or "UNKNOWN")
                reject_reasons[key] += 1

            elif event == "ORDER_CANCELLED":
                reason = str(row.get("reason", "")).strip() or "UNKNOWN"
                cancel_reasons[reason] += 1

    return {
        "event_counts": dict(event_counts),
        "proposed_intents": proposed_intents,
        "strategy_intents": strategy_intents,
        "placed_orders": placed_orders,
        "reject_reasons": reject_reasons,
        "cancel_reasons": cancel_reasons,
    }


def _summarize_report(report_path: Path) -> dict[str, Any]:
    with report_path.open("r", encoding="utf-8") as f:
        report = json.load(f)

    metrics = report.get("metrics", {}) if isinstance(report, dict) else {}
    trades = report.get("trades", []) if isinstance(report, dict) else []
    trades = trades if isinstance(trades, list) else []

    close_reason_counts: Counter[str] = Counter()
    net_profit_sum = 0.0
    gross_profit_sum = 0.0
    gross_loss_abs_sum = 0.0
    wins = 0
    losses = 0

    for tr in trades:
        if not isinstance(tr, dict):
            continue
        reason = str(tr.get("close_reason", "UNKNOWN"))
        close_reason_counts[reason] += 1
        pnl_net = _safe_float(tr.get("pnl_usdt_net"), 0.0)
        net_profit_sum += pnl_net
        if pnl_net > 0:
            wins += 1
            gross_profit_sum += pnl_net
        elif pnl_net < 0:
            losses += 1
            gross_loss_abs_sum += -pnl_net

    reconstructed_trades = len(trades)
    win_rate_calc = (wins / reconstructed_trades) if reconstructed_trades > 0 else 0.0

    return {
        "metrics": metrics,
        "reconstructed_trades": reconstructed_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_calc": win_rate_calc,
        "net_profit_sum": net_profit_sum,
        "gross_profit_sum": gross_profit_sum,
        "gross_loss_abs_sum": gross_loss_abs_sum,
        "close_reason_counts": dict(close_reason_counts),
        "trades_summary": report.get("trades_summary", {}),
        "orders_summary": report.get("orders_summary", {}),
    }


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def _print_human(
    order_log: Path,
    report_path: Optional[Path],
    order_stats: dict[str, Any],
    report_stats: Optional[dict[str, Any]],
    top: int,
) -> None:
    print("=" * 72)
    print("BACKTEST LOG STATS")
    print("=" * 72)
    print(f"order_log: {order_log}")
    print(f"report:    {report_path if report_path else 'not found'}")
    print("-" * 72)

    ec = order_stats["event_counts"]
    print("Orders / Intents:")
    print(f"  proposed_intents (Decision): {order_stats['proposed_intents']}")
    print(f"  strategy_intents (DM source): {order_stats['strategy_intents']}")
    print(f"  placed_orders: {order_stats['placed_orders']}")
    print(f"  rejected_orders: {ec.get('ORDER_REJECTED', 0)}")
    print(f"  cancelled_orders: {ec.get('ORDER_CANCELLED', 0)}")

    rr: Counter[str] = order_stats["reject_reasons"]
    if rr:
        print("Top reject reasons:")
        for reason, cnt in rr.most_common(top):
            print(f"  {cnt:>5}  {reason}")

    cr: Counter[str] = order_stats["cancel_reasons"]
    if cr:
        print("Cancel reasons:")
        for reason, cnt in cr.most_common(top):
            print(f"  {cnt:>5}  {reason}")

    if not report_stats:
        print("-" * 72)
        print("PnL / win-rate unavailable (matching backtest report not found).")
        return

    metrics = report_stats["metrics"]
    print("-" * 72)
    print("Performance:")
    print(f"  total_pnl: {_safe_float(metrics.get('total_pnl')):.2f} USDT")
    print(f"  roi: {_safe_float(metrics.get('roi_pct')):.2f}%")
    print(f"  win_rate (engine): {_safe_float(metrics.get('win_rate')) * 100:.2f}%")
    print(f"  total_trades (engine): {int(_safe_float(metrics.get('total_trades')))}")

    print("Reconstructed trades (from report.trades):")
    print(f"  closed_trades: {report_stats['reconstructed_trades']}")
    print(f"  wins: {report_stats['wins']}")
    print(f"  losses: {report_stats['losses']}")
    print(f"  win_rate (calc): {_fmt_pct(report_stats['win_rate_calc'])}")
    print(f"  net_profit_sum: {report_stats['net_profit_sum']:.2f} USDT")
    print(f"  gross_profit_sum: {report_stats['gross_profit_sum']:.2f} USDT")
    print(f"  gross_loss_sum: -{report_stats['gross_loss_abs_sum']:.2f} USDT")

    close_reasons = report_stats.get("close_reason_counts", {})
    if close_reasons:
        print("Close reasons:")
        for reason, cnt in sorted(close_reasons.items(), key=lambda kv: kv[1], reverse=True)[:top]:
            print(f"  {cnt:>5}  {reason}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize backtest order log + matched report metrics.")
    ap.add_argument("--order-log", type=str, default=None, help="Path to order_log_*.jsonl (default: latest)")
    ap.add_argument("--report", type=str, default=None, help="Path to backtest_*.json (default: auto-match)")
    ap.add_argument("--all", action="store_true", help="Process all existing order_log_*.jsonl files")
    ap.add_argument("--top", type=int, default=8, help="How many top reasons to print")
    ap.add_argument("--json", action="store_true", help="Print JSON instead of human-readable output")
    args = ap.parse_args()

    if args.all and args.order_log:
        raise SystemExit("--all and --order-log are mutually exclusive")

    order_logs = _list_order_logs() if args.all else [_pick_order_log(args.order_log)]
    if not order_logs:
        raise SystemExit(f"No order logs found in {LOGS_DIR}")

    results: list[dict[str, Any]] = []
    for order_log in order_logs:
        report_path = _find_report_for_order_log(order_log, args.report if not args.all else None)
        order_stats = _summarize_order_log(order_log)
        report_stats = _summarize_report(report_path) if report_path else None

        payload = {
            "order_log": str(order_log),
            "report": str(report_path) if report_path else None,
            "order_stats": {
                "event_counts": order_stats["event_counts"],
                "proposed_intents": order_stats["proposed_intents"],
                "strategy_intents": order_stats["strategy_intents"],
                "placed_orders": order_stats["placed_orders"],
                "reject_reasons_top": dict(order_stats["reject_reasons"].most_common(args.top)),
                "cancel_reasons_top": dict(order_stats["cancel_reasons"].most_common(args.top)),
            },
            "report_stats": report_stats,
        }
        results.append(payload)

        if not args.json:
            _print_human(
                order_log=order_log,
                report_path=report_path,
                order_stats=order_stats,
                report_stats=report_stats,
                top=args.top,
            )
            if len(order_logs) > 1:
                print()

    if args.json:
        if len(results) == 1:
            print(json.dumps(results[0], ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"items": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
