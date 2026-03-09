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
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = ROOT / "logs" / "backtests"
REPORTS_DIR = ROOT / "reports" / "backtests"


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _normalize_regime(v: Any) -> str:
    if v is None:
        return "UNKNOWN"
    s = str(v).strip()
    if not s or s.lower() == "null":
        return "UNKNOWN"
    return s


def _get_regime_from_row(row: dict[str, Any]) -> str:
    regime = _normalize_regime(row.get("regime"))
    if regime != "UNKNOWN":
        return regime
    meta = row.get("metadata")
    if isinstance(meta, dict):
        return _normalize_regime(meta.get("regime"))
    return "UNKNOWN"


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
    close_reasons: Counter[str] = Counter()
    
    proposed_intents = 0
    strategy_intents = 0
    placed_orders = 0
    filled_orders = 0
    entry_fills = 0  # ORDER_FILLED where order_kind=ENTRY (excludes bracket SL/TP fills)
    buy_orders = 0
    sell_orders = 0
    
    first_ts = None
    last_ts = None
    
    # Global PnL Tracking
    net_profit_sum = 0.0
    wins = 0
    losses = 0
    peak_pnl = 0.0
    max_drawdown = 0.0
    
    # Regime mappings
    rid_to_regime: dict[str, str] = {}
    order_id_to_regime: dict[str, str] = {}
    regime_sequence: list[str] = []
    
    # Per-Coin Performance
    symbol_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "net_profit": 0.0,
            "gross_profit": 0.0,
            "gross_loss_abs": 0.0,
        }
    )
    
    regime_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "strategy_intents": 0,
            "proposed_intents": 0,
            "placed_orders": 0,
            "rejected_orders": 0,
            "cancelled_orders": 0,
            "reject_reasons": Counter(),
            "cancel_reasons": Counter(),
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "net_profit": 0.0,
            "gross_profit": 0.0,
            "gross_loss_abs": 0.0,
        }
    )

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

            rid = str(row.get("rid", "")).strip()
            row_regime = _get_regime_from_row(row)
            if rid and row_regime != "UNKNOWN":
                rid_to_regime[rid] = row_regime

            event_counts[event] += 1
            symbol = str(row.get("symbol", "UNKNOWN")).strip()
            
            ts = row.get("timestamp")
            if ts and event != "BOOT":  # BOOT uses wall-clock at session start, exclude from sim time range
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts

            if event == "ORDER_INTENT":
                meta = row.get("metadata", {})
                source = str(row.get("source_fsm", ""))
                if isinstance(meta, dict) and bool(meta.get("intent_proposed")):
                    proposed_intents += 1
                if source == "DecisionMaking":
                    strategy_intents += 1
                    regime = row_regime if row_regime != "UNKNOWN" else rid_to_regime.get(rid, "UNKNOWN")
                    regime_sequence.append(regime)
                    bucket = regime_stats[regime]
                    bucket["strategy_intents"] += 1
                    if isinstance(meta, dict) and bool(meta.get("intent_proposed")):
                        bucket["proposed_intents"] += 1

            elif event == "ORDER_PLACED":
                placed_orders += 1
                regime = row_regime if row_regime != "UNKNOWN" else rid_to_regime.get(rid, "UNKNOWN")
                bucket = regime_stats[regime]
                bucket["placed_orders"] += 1
                order_id = str(row.get("order_id", "")).strip()
                if order_id:
                    order_id_to_regime[order_id] = regime
                
                side = str(row.get("side", "")).strip().upper()
                if side == "BUY":
                    buy_orders += 1
                elif side == "SELL":
                    sell_orders += 1
                    
            elif event == "ORDER_FILLED":
                filled_orders += 1
                ok = row.get("order_kind") or row.get("close_reason", "")
                if ok in ("ENTRY", "ENTRY_FILLED"):
                    entry_fills += 1

            elif event == "ORDER_REJECTED":
                nrr = str(row.get("nrr_code", "")).strip()
                why = str(row.get("why", "")).strip()
                
                # Aggregate reason without floating point confidences to avoid hundreds of unique keys
                why_base = why.split(" regime_confidence=")[0].rstrip(": ") if " regime_confidence=" in why else why
                key = f"{nrr} | {why_base}" if nrr else (why_base or "UNKNOWN")
                
                reject_reasons[key] += 1
                regime = row_regime if row_regime != "UNKNOWN" else rid_to_regime.get(rid, "UNKNOWN")
                bucket = regime_stats[regime]
                bucket["rejected_orders"] += 1
                bucket["reject_reasons"][key] += 1

            elif event == "ORDER_CANCELLED":
                reason = str(row.get("reason", "")).strip() or "UNKNOWN"
                cancel_reasons[reason] += 1
                order_id = str(row.get("order_id", "")).strip()
                regime = order_id_to_regime.get(order_id, "UNKNOWN")
                if regime == "UNKNOWN":
                    regime = row_regime if row_regime != "UNKNOWN" else rid_to_regime.get(rid, "UNKNOWN")
                bucket = regime_stats[regime]
                bucket["cancelled_orders"] += 1
                bucket["cancel_reasons"][reason] += 1

            elif event == "POSITION_CLOSED":
                reason = str(row.get("why", "UNKNOWN")).strip()
                close_reasons[reason] += 1
                
                meta = row.get("metadata", {})
                if isinstance(meta, dict):
                    pnl = _safe_float(meta.get("realized_pnl"), 0.0)
                    if pnl != 0.0:  # Only count actual PnL changes
                        net_profit_sum += pnl
                        
                        # Drawdown Calculation
                        if net_profit_sum > peak_pnl:
                            peak_pnl = net_profit_sum
                        else:
                            current_drawdown = peak_pnl - net_profit_sum
                            if current_drawdown > max_drawdown:
                                max_drawdown = current_drawdown
                        
                        sym_bucket = symbol_stats[symbol]
                        sym_bucket["trades"] += 1
                        sym_bucket["net_profit"] += pnl
                        
                        regime = row_regime if row_regime != "UNKNOWN" else rid_to_regime.get(rid, "UNKNOWN")
                        reg_bucket = regime_stats[regime]
                        reg_bucket["trades"] += 1
                        reg_bucket["net_profit"] += pnl
                        
                        if pnl > 0:
                            wins += 1
                            sym_bucket["wins"] += 1
                            sym_bucket["gross_profit"] += pnl
                            reg_bucket["wins"] += 1
                            reg_bucket["gross_profit"] += pnl
                        else:
                            losses += 1
                            sym_bucket["losses"] += 1
                            sym_bucket["gross_loss_abs"] += abs(pnl)
                            reg_bucket["losses"] += 1
                            reg_bucket["gross_loss_abs"] += abs(pnl)

    regime_switches = 0
    prev_regime: Optional[str] = None
    for regime in regime_sequence:
        if prev_regime is not None and regime != prev_regime:
            regime_switches += 1
        prev_regime = regime

    # Finalize regime stats
    regime_stats_out: dict[str, Any] = {}
    for regime, stats in regime_stats.items():
        tr_count = int(stats["trades"])
        win_rate = (float(stats["wins"]) / tr_count) if tr_count > 0 else 0.0
        regime_stats_out[regime] = {
            "strategy_intents": int(stats["strategy_intents"]),
            "proposed_intents": int(stats["proposed_intents"]),
            "placed_orders": int(stats["placed_orders"]),
            "rejected_orders": int(stats["rejected_orders"]),
            "cancelled_orders": int(stats["cancelled_orders"]),
            "reject_reasons": dict(stats["reject_reasons"]),
            "cancel_reasons": dict(stats["cancel_reasons"]),
            "trades": tr_count,
            "wins": int(stats["wins"]),
            "losses": int(stats["losses"]),
            "win_rate": win_rate,
            "net_profit": float(stats["net_profit"]),
            "gross_profit": float(stats["gross_profit"]),
            "gross_loss_abs": float(stats["gross_loss_abs"]),
        }

    # Finalize symbol stats
    symbol_stats_out: dict[str, Any] = {}
    for sym, stats in symbol_stats.items():
        tr_count = int(stats["trades"])
        win_rate = (float(stats["wins"]) / tr_count) if tr_count > 0 else 0.0
        profit_factor = float(stats["gross_profit"]) / float(stats["gross_loss_abs"]) if float(stats["gross_loss_abs"]) > 0 else float('inf')
        symbol_stats_out[sym] = {
            "trades": tr_count,
            "wins": int(stats["wins"]),
            "losses": int(stats["losses"]),
            "win_rate": win_rate,
            "net_profit": float(stats["net_profit"]),
            "profit_factor": profit_factor
        }

    # Only include UNKNOWN regime if there was actual activity
    known_regimes = sorted([r for r in regime_stats_out.keys() if r != "UNKNOWN"])
    if "UNKNOWN" in regime_stats_out:
        u_stats = regime_stats_out["UNKNOWN"]
        if u_stats["strategy_intents"] > 0 or u_stats["placed_orders"] > 0 or u_stats["rejected_orders"] > 0 or u_stats["trades"] > 0:
            known_regimes.append("UNKNOWN")
    total_trades = wins + losses
    overall_win_rate = (wins / total_trades) if total_trades > 0 else 0.0

    return {
        "event_counts": dict(event_counts),
        "proposed_intents": proposed_intents,
        "strategy_intents": strategy_intents,
        "placed_orders": placed_orders,
        "filled_orders": filled_orders,
        "entry_fills": entry_fills,
        "buy_orders": buy_orders,
        "sell_orders": sell_orders,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "reject_reasons": reject_reasons,
        "cancel_reasons": cancel_reasons,
        "close_reasons": close_reasons,
        "session_regime_count": len(known_regimes),
        "session_regimes": known_regimes,
        "regime_switches": regime_switches,
        "regime_stats": regime_stats_out,
        "symbol_stats": symbol_stats_out,
        "performance": {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": overall_win_rate,
            "net_profit": net_profit_sum,
            "max_drawdown": max_drawdown
        }
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
    regime_trade_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "net_profit_sum": 0.0,
            "gross_profit_sum": 0.0,
            "gross_loss_abs_sum": 0.0,
            "close_reasons": Counter(),
        }
    )

    for tr in trades:
        if not isinstance(tr, dict):
            continue
        reason = str(tr.get("close_reason", "UNKNOWN"))
        close_reason_counts[reason] += 1
        pnl_net = _safe_float(tr.get("pnl_usdt_net"), 0.0)
        net_profit_sum += pnl_net
        regime = _normalize_regime(tr.get("market_regime"))
        regime_bucket = regime_trade_stats[regime]
        regime_bucket["trades"] += 1
        regime_bucket["net_profit_sum"] += pnl_net
        regime_bucket["close_reasons"][reason] += 1
        if pnl_net > 0:
            wins += 1
            gross_profit_sum += pnl_net
            regime_bucket["wins"] += 1
            regime_bucket["gross_profit_sum"] += pnl_net
        elif pnl_net < 0:
            losses += 1
            gross_loss_abs_sum += -pnl_net
            regime_bucket["losses"] += 1
            regime_bucket["gross_loss_abs_sum"] += -pnl_net

    reconstructed_trades = len(trades)
    win_rate_calc = (wins / reconstructed_trades) if reconstructed_trades > 0 else 0.0

    regime_trade_stats_out: dict[str, Any] = {}
    for regime, stats in regime_trade_stats.items():
        trades_count = int(stats["trades"])
        win_rate = (float(stats["wins"]) / trades_count) if trades_count > 0 else 0.0
        regime_trade_stats_out[regime] = {
            "trades": trades_count,
            "wins": int(stats["wins"]),
            "losses": int(stats["losses"]),
            "win_rate": win_rate,
            "net_profit_sum": float(stats["net_profit_sum"]),
            "gross_profit_sum": float(stats["gross_profit_sum"]),
            "gross_loss_abs_sum": float(stats["gross_loss_abs_sum"]),
            "close_reasons": dict(stats["close_reasons"]),
        }

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
        "regime_trade_stats": regime_trade_stats_out,
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
    print("BACKTEST LOG STATS (Extracted Privately From Logs)")
    print("=" * 72)
    print(f"order_log: {order_log}")
    print("-" * 72)

    perf = order_stats["performance"]
    print("PERFORMANCE METRICS:")
    print(f"  total_trades (closed): {perf['total_trades']}")
    print(f"  net_profit_sum:      {perf['net_profit']:.2f} USDT")
    print(f"  win_rate:            {_fmt_pct(perf['win_rate'])}  ({perf['wins']}W / {perf['losses']}L)")
    print(f"  max_drawdown:        {perf['max_drawdown']:.2f} USDT")

    syms = order_stats.get("symbol_stats", {})
    if syms:
        print("\nPER-COIN PERFORMANCE:")
        sorted_syms = sorted(syms.items(), key=lambda kv: kv[1]["net_profit"], reverse=True)
        for sym, stat in sorted_syms:
            pf = stat["profit_factor"]
            pf_str = f"{pf:.2f}" if pf != float('inf') else "INF"
            print(f"  {sym:<10} PnL: {stat['net_profit']:>8.2f} USDT | WR: {_fmt_pct(stat['win_rate']):>7} ({stat['wins']:>2}W/{stat['losses']:>2}L) | PF: {pf_str:<5}")

    first_ts = order_stats.get("first_ts")
    last_ts = order_stats.get("last_ts")
    if first_ts and last_ts:
        import datetime
        start_dt = datetime.datetime.fromtimestamp(first_ts / 1000.0, datetime.timezone.utc)
        end_dt = datetime.datetime.fromtimestamp(last_ts / 1000.0, datetime.timezone.utc)
        duration = end_dt - start_dt
        print("\nTIME CONTEXT:")
        print(f"  Start:    {start_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"  End:      {end_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"  Duration: {duration}")

    print("-" * 72)
    ec = order_stats["event_counts"]
    proposed = order_stats.get('proposed_intents', 0)
    placed = order_stats.get('placed_orders', 0)
    filled = order_stats.get('filled_orders', 0)
    entry_filled = order_stats.get('entry_fills', 0)
    closed = ec.get('POSITION_CLOSED', 0)
    rejected = ec.get('ORDER_REJECTED', 0)
    cancelled = ec.get('ORDER_CANCELLED', 0)
    bracket_fills = filled - entry_filled

    total = proposed + rejected

    print("FUNNEL / CONVERSION:")
    print(f"  Signals generated:     {total}  (Proposed + Rejected)")
    if total > 0:
        print(f"  |- Rejected:            {rejected}  ({(rejected/total)*100:.1f}%)")
        print(f"  |- Intents proposed:    {proposed}  ({(proposed/total)*100:.1f}%)")
        if proposed > 0:
            print(f"  |- Orders placed:       {placed}  ({(placed/proposed)*100:.1f}%)")
            if placed > 0:
                print(f"  |  |- Cancelled:        {cancelled}  ({(cancelled/placed)*100:.1f}%)")
                print(f"  |  |- Entries filled:   {entry_filled}  ({(entry_filled/placed)*100:.1f}%)")
                if bracket_fills > 0:
                    print(f"  |  |  |- Bracket fills: {bracket_fills}  (SL/TP on filled entries)")
                pending = placed - cancelled - entry_filled
                print(f"  |  \\- Pending/Expired:  {max(pending,0)}  ({(max(pending,0)/placed)*100:.1f}%)")
            else:
                print(f"  |  |- Cancelled:        0")
                print(f"  |  |- Entries filled:   0")
        else:
            print(f"  |- Orders placed:       0")
        print(f"  \\- Positions closed:    {closed}")
    else:
        print("  No signals generated.")

    print("\nSIDE DISTRIBUTION (Placed Orders):")
    print(f"  BUY:  {order_stats.get('buy_orders', 0)}")
    print(f"  SELL: {order_stats.get('sell_orders', 0)}")

    rr: Counter[str] = order_stats["reject_reasons"]
    if rr:
        print("\nTOP REJECT REASONS:")
        for reason, cnt in rr.most_common(top):
            print(f"  {cnt:>5}  {reason}")

    cl: Counter[str] = order_stats["close_reasons"]
    if cl:
        print("\nTOP CLOSE REASONS:")
        for reason, cnt in cl.most_common(top):
            print(f"  {cnt:>5}  {reason}")

    print("\nREGIME OVERVIEW:")
    print(f"  regime_list: {', '.join(order_stats.get('session_regimes', []))}")
    print(f"  regime_switches: {order_stats.get('regime_switches', 0)}")

    regime_stats = order_stats.get("regime_stats", {})
    if regime_stats:
        print("\nPERFORMANCE BY REGIME:")
        sorted_regimes = sorted(
            regime_stats.items(),
            key=lambda kv: kv[1].get("net_profit", 0),
            reverse=True,
        )
        for regime, stats in sorted_regimes:
            rej = stats.get('rejected_orders', 0)
            print(f"  [{regime}]")
            print(
                "    "
                f"PnL: {stats.get('net_profit', 0.0):.2f} USDT | "
                f"WR: {_fmt_pct(stats.get('win_rate', 0.0))} "
                f"({stats.get('wins', 0)}W/{stats.get('losses', 0)}L) | "
                f"trades={stats.get('trades', 0)} "
                f"intents={stats.get('strategy_intents', 0)} "
                f"placed={stats.get('placed_orders', 0)}"
                + (f" rejected={rej}" if rej > 0 else "")
            )


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
                "session_regime_count": order_stats["session_regime_count"],
                "session_regimes": order_stats["session_regimes"],
                "regime_switches": order_stats["regime_switches"],
                "regime_stats": order_stats["regime_stats"],
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
