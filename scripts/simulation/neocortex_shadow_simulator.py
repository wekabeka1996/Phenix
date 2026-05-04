#!/usr/bin/env python3
"""
Neocortex Shadow Intent simulator (Phase 4 analytics).

Generates reproducible trade-level simulation from:
- data/shadow_intents.jsonl* (LONG/SHORT/FLAT intents)
- logs/features/*.log (price stream)

Output artifacts:
- reports/neocortex_shadow_simulation_<timestamp>.csv
- reports/neocortex_shadow_simulation_summary_<timestamp>.md
"""

from __future__ import annotations

import argparse
import bisect
import csv
import glob
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PRICE_KEYS = ("price", "mid_price", "mark_price", "close", "last_price")


@dataclass
class Tick:
    idx: int
    price: float
    ts: Optional[float]


@dataclass
class Intent:
    idx: int
    symbol: str
    action: str
    ts: Optional[float]


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts_from_prefix(line: str) -> Optional[float]:
    # Format: YYYY-MM-DD HH:MM:SS,mmm - ...
    if len(line) < 23:
        return None
    prefix = line[:23]
    try:
        dt = datetime.strptime(prefix, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None
    return dt.timestamp()


def _extract_price(features: Dict[str, Any]) -> Optional[float]:
    for key in PRICE_KEYS:
        value = features.get(key)
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def load_feature_ticks(features_dir: Path) -> Dict[str, List[Tick]]:
    by_symbol: Dict[str, List[Tick]] = {}
    for path in sorted(features_dir.glob("*.log")):
        symbol = path.stem.strip().upper()
        ticks: List[Tick] = []
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                ts = _parse_ts_from_prefix(line)
                payload: Optional[Dict[str, Any]] = None

                if line.startswith("{"):
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    payload = obj if isinstance(obj, dict) else None
                else:
                    pos = line.find("{")
                    if pos < 0:
                        continue
                    try:
                        obj = json.loads(line[pos:])
                    except json.JSONDecodeError:
                        continue
                    payload = obj if isinstance(obj, dict) else None

                if payload is None:
                    continue

                price = _extract_price(payload)
                if price is None:
                    continue
                ticks.append(Tick(idx=len(ticks), price=price, ts=ts))

        if ticks:
            by_symbol[symbol] = ticks
    return by_symbol


def load_shadow_intents(intents_glob: str) -> List[Intent]:
    paths = [Path(p) for p in glob.glob(intents_glob)]
    paths.sort(key=lambda p: (p.stat().st_mtime, str(p)))
    intents: List[Intent] = []
    idx = 0
    for path in paths:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                symbol = str(obj.get("symbol", "")).strip().upper()
                action = str(obj.get("action_name", "")).strip().upper()
                if not symbol or action not in {"LONG", "SHORT", "FLAT"}:
                    continue
                ts = _safe_float(obj.get("source_ts"))
                if ts is None:
                    ts = _safe_float(obj.get("timestamp"))
                intents.append(Intent(idx=idx, symbol=symbol, action=action, ts=ts))
                idx += 1
    return intents


def pick_time_mode(mode: str, ticks_by_symbol: Dict[str, List[Tick]], intents: List[Intent]) -> str:
    if mode in {"sequence_time", "wall_clock_time"}:
        return mode
    if not intents:
        return "sequence_time"

    symbols = {intent.symbol for intent in intents if intent.symbol in ticks_by_symbol}
    if not symbols:
        return "sequence_time"

    missing_ts_ticks = 0
    total_ticks = 0
    for symbol in symbols:
        for tick in ticks_by_symbol.get(symbol, []):
            total_ticks += 1
            if tick.ts is None:
                missing_ts_ticks += 1
    if total_ticks == 0 or missing_ts_ticks > 0:
        return "sequence_time"

    for intent in intents:
        if intent.symbol not in ticks_by_symbol:
            continue
        if intent.ts is None:
            return "sequence_time"
    return "wall_clock_time"


def _anchor_by_time(ticks: List[Tick], ts: float) -> int:
    ts_values = [tick.ts for tick in ticks]
    idx = bisect.bisect_left(ts_values, ts)
    if idx >= len(ticks):
        return len(ticks) - 1
    return idx


def _entry_exec_price(side: str, mid_price: float, entry_slip: float) -> float:
    if side == "LONG":
        return mid_price * (1.0 + entry_slip)
    return mid_price * (1.0 - entry_slip)


def _exit_exec_price(side: str, mid_price: float, exit_slip: float) -> float:
    if side == "LONG":
        return mid_price * (1.0 - exit_slip)
    return mid_price * (1.0 + exit_slip)


def _returns(side: str, entry_mid: float, exit_mid: float, entry_exec: float, exit_exec: float) -> Tuple[float, float]:
    if side == "LONG":
        raw = (exit_mid / entry_mid) - 1.0
        exec_r = (exit_exec / entry_exec) - 1.0
    else:
        raw = (entry_mid / exit_mid) - 1.0
        exec_r = (entry_exec / exit_exec) - 1.0
    return raw, exec_r


def simulate_symbol(
    symbol: str,
    ticks: List[Tick],
    intents: List[Intent],
    *,
    mode: str,
    horizon_ticks: int,
    fee_bps_roundtrip: float,
    slippage_bps_entry: float,
    slippage_bps_exit: float,
) -> List[Dict[str, Any]]:
    if len(ticks) < 2 or not intents:
        return []

    fee_rate = fee_bps_roundtrip / 10000.0
    entry_slip = slippage_bps_entry / 10000.0
    exit_slip = slippage_bps_exit / 10000.0

    local_intents = [intent for intent in intents if intent.symbol == symbol]
    if not local_intents:
        return []

    anchors: List[int] = []
    for seq_idx, intent in enumerate(local_intents):
        if mode == "wall_clock_time" and intent.ts is not None:
            anchors.append(_anchor_by_time(ticks, intent.ts))
        else:
            anchors.append(min(seq_idx, len(ticks) - 1))

    trades: List[Dict[str, Any]] = []
    open_trade: Optional[Dict[str, Any]] = None

    def close_trade(close_idx: int, reason: str, close_intent_idx: Optional[int]) -> None:
        nonlocal open_trade
        if open_trade is None:
            return

        close_idx = min(max(0, close_idx), len(ticks) - 1)
        entry_idx = open_trade["entry_idx"]
        if close_idx <= entry_idx:
            close_idx = min(entry_idx + 1, len(ticks) - 1)
            if close_idx <= entry_idx:
                open_trade = None
                return

        side = open_trade["side"]
        entry_mid = ticks[entry_idx].price
        exit_mid = ticks[close_idx].price
        entry_exec = _entry_exec_price(side, entry_mid, entry_slip)
        exit_exec = _exit_exec_price(side, exit_mid, exit_slip)
        raw_return, exec_return = _returns(side, entry_mid, exit_mid, entry_exec, exit_exec)
        slippage_return = raw_return - exec_return
        net_return = exec_return - fee_rate
        pnl_quote = net_return * entry_mid

        trades.append(
            {
                "symbol": symbol,
                "side": side,
                "entry_intent_idx": open_trade["intent_idx"],
                "close_intent_idx": close_intent_idx,
                "entry_seq_idx": entry_idx,
                "exit_seq_idx": close_idx,
                "entry_price_mid": entry_mid,
                "exit_price_mid": exit_mid,
                "raw_return": raw_return,
                "slippage_return": slippage_return,
                "fee_return": fee_rate,
                "net_return": net_return,
                "pnl_quote_1unit": pnl_quote,
                "reason": reason,
                "time_mode": mode,
            }
        )
        open_trade = None

    for i, intent in enumerate(local_intents):
        anchor = anchors[i]

        if open_trade is not None and open_trade["horizon_idx"] <= anchor:
            close_trade(open_trade["horizon_idx"], "horizon", None)

        action = intent.action
        if action not in {"LONG", "SHORT", "FLAT"}:
            continue

        if action == "FLAT":
            if open_trade is not None:
                close_trade(anchor + 1, "flat_intent", intent.idx)
            continue

        desired_side = action
        entry_idx = min(anchor + 1, len(ticks) - 1)
        if entry_idx <= anchor:
            continue

        if open_trade is None:
            open_trade = {
                "side": desired_side,
                "entry_idx": entry_idx,
                "horizon_idx": min(entry_idx + horizon_ticks, len(ticks) - 1),
                "intent_idx": intent.idx,
            }
            continue

        if open_trade["side"] == desired_side:
            continue

        close_trade(entry_idx, f"reverse_to_{desired_side.lower()}", intent.idx)
        open_trade = {
            "side": desired_side,
            "entry_idx": entry_idx,
            "horizon_idx": min(entry_idx + horizon_ticks, len(ticks) - 1),
            "intent_idx": intent.idx,
        }

    if open_trade is not None:
        horizon_idx = open_trade["horizon_idx"]
        reason = "horizon" if horizon_idx < len(ticks) - 1 else "data_end"
        close_trade(horizon_idx, reason, None)

    return trades


def _drawdown(returns: List[float]) -> float:
    peak = 0.0
    equity = 0.0
    worst = 0.0
    for r in returns:
        equity += r
        peak = max(peak, equity)
        dd = equity - peak
        if dd < worst:
            worst = dd
    return worst


def summarize(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0.0,
            "net_return_sum": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "avg_pnl_quote": 0.0,
        }
    net = [float(t["net_return"]) for t in trades]
    wins = sum(1 for r in net if r > 0)
    losses = sum(1 for r in net if r < 0)
    trades_n = len(net)
    net_sum = sum(net)
    return {
        "trades": trades_n,
        "wins": wins,
        "losses": losses,
        "winrate": (wins / trades_n) if trades_n > 0 else 0.0,
        "net_return_sum": net_sum,
        "expectancy": (net_sum / trades_n) if trades_n > 0 else 0.0,
        "max_drawdown": _drawdown(net),
        "avg_pnl_quote": sum(float(t["pnl_quote_1unit"]) for t in trades) / trades_n,
    }


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "symbol",
        "side",
        "entry_intent_idx",
        "close_intent_idx",
        "entry_seq_idx",
        "exit_seq_idx",
        "entry_price_mid",
        "exit_price_mid",
        "raw_return",
        "slippage_return",
        "fee_return",
        "net_return",
        "pnl_quote_1unit",
        "reason",
        "time_mode",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_summary(
    path: Path,
    *,
    mode: str,
    intents_count: int,
    trades: List[Dict[str, Any]],
    per_symbol: Dict[str, Dict[str, Any]],
    args: argparse.Namespace,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    overall = summarize(trades)
    lines: List[str] = []
    lines.append("# Neocortex Shadow Simulation Summary")
    lines.append("")
    lines.append(f"- Generated at: `{datetime.utcnow().isoformat()}Z`")
    lines.append(f"- Time mode: `{mode}`")
    lines.append(f"- Intents loaded: `{intents_count}`")
    lines.append(f"- Trades simulated: `{overall['trades']}`")
    lines.append("")
    lines.append("## Parameters")
    lines.append("")
    lines.append(f"- horizon_ticks: `{args.horizon_ticks}`")
    lines.append(f"- fee_bps_roundtrip: `{args.fee_bps_roundtrip}`")
    lines.append(f"- slippage_bps_entry: `{args.slippage_bps_entry}`")
    lines.append(f"- slippage_bps_exit: `{args.slippage_bps_exit}`")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append(f"- winrate: `{overall['winrate'] * 100:.2f}%`")
    lines.append(f"- net_return_sum: `{overall['net_return_sum'] * 10000:.2f} bps`")
    lines.append(f"- expectancy: `{overall['expectancy'] * 10000:.2f} bps/trade`")
    lines.append(f"- max_drawdown: `{overall['max_drawdown'] * 10000:.2f} bps`")
    lines.append(f"- avg_pnl_quote_1unit: `{overall['avg_pnl_quote']:.6f}`")
    lines.append("")
    lines.append("## By Symbol")
    lines.append("")
    lines.append("| Symbol | Trades | Winrate | Net bps | Expectancy bps | Max DD bps |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for symbol in sorted(per_symbol.keys()):
        s = per_symbol[symbol]
        lines.append(
            f"| {symbol} | {s['trades']} | {s['winrate'] * 100:.2f}% | "
            f"{s['net_return_sum'] * 10000:.2f} | {s['expectancy'] * 10000:.2f} | "
            f"{s['max_drawdown'] * 10000:.2f} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- If feature logs do not contain reliable timestamps, mode is `sequence_time` "
        "and alignment is based on per-symbol intent order, not wall-clock."
    )
    lines.append(
        "- This is shadow analytics and does not replace realized exchange PnL accounting."
    )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Neocortex shadow intent simulator")
    parser.add_argument("--intents-glob", default="data/shadow_intents.jsonl*")
    parser.add_argument("--features-dir", default="logs/features")
    parser.add_argument("--mode", choices=["auto", "sequence_time", "wall_clock_time"], default="auto")
    parser.add_argument("--horizon-ticks", type=int, default=120)
    parser.add_argument("--fee-bps-roundtrip", type=float, default=4.0)
    parser.add_argument("--slippage-bps-entry", type=float, default=1.0)
    parser.add_argument("--slippage-bps-exit", type=float, default=1.0)
    parser.add_argument("--output-dir", default="reports")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    features_dir = Path(args.features_dir)
    if not features_dir.exists():
        raise SystemExit(f"features directory not found: {features_dir}")

    intents = load_shadow_intents(args.intents_glob)
    ticks_by_symbol = load_feature_ticks(features_dir)
    mode = pick_time_mode(args.mode, ticks_by_symbol, intents)

    simulated: List[Dict[str, Any]] = []
    symbols = sorted(set(intent.symbol for intent in intents if intent.symbol in ticks_by_symbol))
    for symbol in symbols:
        symbol_trades = simulate_symbol(
            symbol,
            ticks_by_symbol[symbol],
            intents,
            mode=mode,
            horizon_ticks=int(args.horizon_ticks),
            fee_bps_roundtrip=float(args.fee_bps_roundtrip),
            slippage_bps_entry=float(args.slippage_bps_entry),
            slippage_bps_exit=float(args.slippage_bps_exit),
        )
        simulated.extend(symbol_trades)

    per_symbol: Dict[str, Dict[str, Any]] = {}
    for symbol in symbols:
        per_symbol[symbol] = summarize([t for t in simulated if t["symbol"] == symbol])

    out_dir = Path(args.output_dir)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"neocortex_shadow_simulation_{stamp}.csv"
    md_path = out_dir / f"neocortex_shadow_simulation_summary_{stamp}.md"
    write_csv(csv_path, simulated)
    write_summary(
        md_path,
        mode=mode,
        intents_count=len(intents),
        trades=simulated,
        per_symbol=per_symbol,
        args=args,
    )

    print(f"Simulation complete: trades={len(simulated)} mode={mode}")
    print(f"CSV: {csv_path}")
    print(f"Summary: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

