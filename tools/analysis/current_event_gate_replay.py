from __future__ import annotations

import csv
import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs"
OUT_DIR = ROOT / "calibrators" / "datasets" / "current_event_gate_replay"
FEE_AND_SLIPPAGE_BPS = 10.0


def _load_jsonl(path: Path):
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_no, json.loads(line)
            except json.JSONDecodeError:
                continue


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def _side_sign(side: str | None) -> int:
    s = str(side or "").upper()
    return 1 if s in {"BUY", "LONG"} else -1


def _pnl_bps(side: str, entry: float, exit_price: float) -> float:
    sign = _side_sign(side)
    return sign * (exit_price - entry) / entry * 10_000.0


@dataclass
class Bar:
    ts_ms: int
    symbol: str
    o: float
    h: float
    l: float
    c: float
    mr_regime: str | None
    mr_signal: str | None
    mr_reason: str | None
    pct_b: float | None
    rsi: float | None
    atr: float | None


def load_bars() -> dict[str, list[Bar]]:
    bars_by_symbol: dict[str, list[Bar]] = defaultdict(list)
    for _, row in _load_jsonl(LOGS / "mean_reversion" / "bars_300s.jsonl"):
        ohlcv = row.get("ohlcv") or {}
        indicators = row.get("indicators") or {}
        bb = indicators.get("bb") or {}
        signal = row.get("signal") or {}
        try:
            bar = Bar(
                ts_ms=int(row["ts_ms"]),
                symbol=str(row["symbol"]),
                o=float(ohlcv["o"]),
                h=float(ohlcv["h"]),
                l=float(ohlcv["l"]),
                c=float(ohlcv["c"]),
                mr_regime=signal.get("regime"),
                mr_signal=signal.get("type"),
                mr_reason=signal.get("reason"),
                pct_b=_float(bb.get("pct_b")),
                rsi=_float(indicators.get("rsi")),
                atr=_float(indicators.get("atr")),
            )
        except (KeyError, TypeError, ValueError):
            continue
        bars_by_symbol[bar.symbol].append(bar)
    for bars in bars_by_symbol.values():
        bars.sort(key=lambda b: b.ts_ms)
    return bars_by_symbol


def first_bar_index_at_or_after(bars: list[Bar], ts_ms: int) -> int | None:
    lo, hi = 0, len(bars)
    while lo < hi:
        mid = (lo + hi) // 2
        if bars[mid].ts_ms < ts_ms:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(bars) else None


def prior_bar(bars: list[Bar], ts_ms: int) -> Bar | None:
    idx = first_bar_index_at_or_after(bars, ts_ms)
    if idx is None:
        return bars[-1] if bars else None
    if bars[idx].ts_ms == ts_ms:
        return bars[idx]
    if idx > 0:
        return bars[idx - 1]
    return bars[idx]


def directional_replay(
    bars: list[Bar],
    side: str,
    basis_ts_ms: int,
    entry: float | None,
    horizons: tuple[int, ...] = (1, 3, 6, 12),
) -> dict[str, float | None]:
    idx = first_bar_index_at_or_after(bars, basis_ts_ms + 1)
    if idx is None:
        return {f"ret_{h}bar_bps": None for h in horizons}
    if entry is None:
        entry = bars[idx].o
    out: dict[str, float | None] = {}
    for h in horizons:
        j = idx + h - 1
        out[f"ret_{h}bar_bps"] = _pnl_bps(side, entry, bars[j].c) if j < len(bars) else None
    return out


def bracket_replay(
    bars: list[Bar],
    side: str,
    basis_ts_ms: int,
    entry: float,
    target: float,
    stop: float,
    max_bars: int = 12,
) -> dict[str, Any]:
    idx = first_bar_index_at_or_after(bars, basis_ts_ms + 1)
    if idx is None:
        return {"outcome": "NO_FUTURE_BARS", "gross_bps": None, "net_bps": None, "bars_held": None}
    side_u = str(side).upper()
    for offset, bar in enumerate(bars[idx: idx + max_bars], 1):
        if side_u in {"BUY", "LONG"}:
            tp_hit = bar.h >= target
            sl_hit = bar.l <= stop
        else:
            tp_hit = bar.l <= target
            sl_hit = bar.h >= stop
        if tp_hit and sl_hit:
            gross = _pnl_bps(side_u, entry, stop)
            return {
                "outcome": "BOTH_HIT_CONSERVATIVE_SL",
                "gross_bps": gross,
                "net_bps": gross - FEE_AND_SLIPPAGE_BPS,
                "bars_held": offset,
                "exit_ts_ms": bar.ts_ms,
                "exit_price": stop,
            }
        if tp_hit:
            gross = _pnl_bps(side_u, entry, target)
            return {
                "outcome": "TP",
                "gross_bps": gross,
                "net_bps": gross - FEE_AND_SLIPPAGE_BPS,
                "bars_held": offset,
                "exit_ts_ms": bar.ts_ms,
                "exit_price": target,
            }
        if sl_hit:
            gross = _pnl_bps(side_u, entry, stop)
            return {
                "outcome": "SL",
                "gross_bps": gross,
                "net_bps": gross - FEE_AND_SLIPPAGE_BPS,
                "bars_held": offset,
                "exit_ts_ms": bar.ts_ms,
                "exit_price": stop,
            }
    last_idx = min(idx + max_bars - 1, len(bars) - 1)
    last = bars[last_idx]
    gross = _pnl_bps(side_u, entry, last.c)
    return {
        "outcome": "TIMEOUT",
        "gross_bps": gross,
        "net_bps": gross - FEE_AND_SLIPPAGE_BPS,
        "bars_held": last_idx - idx + 1,
        "exit_ts_ms": last.ts_ms,
        "exit_price": last.c,
    }


def extract_order_events(
    bars_by_symbol: dict[str, list[Bar]],
    *,
    since_ms: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, event in _load_jsonl(LOGS / "order_log_v1.jsonl"):
        event_type = event.get("event_type")
        if event_type not in {"DECISION_INTENT_REJECTED", "ORDER_INTENT"}:
            continue
        symbol = str(event.get("symbol") or "")
        if not symbol or symbol == "_SYSTEM_":
            continue
        ts_ms = int(event.get("timestamp") or event.get("ts_ms") or 0)
        if since_ms is not None and ts_ms < since_ms:
            continue
        side = str(event.get("side") or "")
        metadata = event.get("metadata") or {}
        low_vol = metadata.get("low_vol_cost_floor") or {}
        economics = low_vol.get("economics_context") or low_vol
        entry = _float(economics.get("entry_price")) or _float(event.get("price"))
        target = _float(economics.get("target_price"))
        stop = _float(economics.get("stop_price"))
        regime_event = ((event.get("regime_provenance") or {}).get("detector_event") or {})
        basis_ts = int(regime_event.get("bar_close_ts_ms") or ts_ms)
        bars = bars_by_symbol.get(symbol, [])
        mr_bar = prior_bar(bars, basis_ts)
        directional = directional_replay(bars, side, basis_ts, entry)
        bracket = None
        if event_type == "DECISION_INTENT_REJECTED" and entry and target and stop:
            bracket = bracket_replay(bars, side, basis_ts, entry, target, stop)
        rows.append({
            "line_no": line_no,
            "rid": event.get("rid"),
            "event_type": event_type,
            "symbol": symbol,
            "strategy_id": event.get("strategy_id"),
            "side": side,
            "ts_ms": ts_ms,
            "ts_utc": _iso(ts_ms),
            "basis_ts_ms": basis_ts,
            "nrr_code": event.get("nrr_code") or metadata.get("deny_reason"),
            "why": event.get("why"),
            "regime": event.get("regime"),
            "regime_confidence": event.get("regime_confidence"),
            "reject_reason": metadata.get("reject_reason"),
            "entry": entry,
            "target": target,
            "stop": stop,
            "direction_confidence": low_vol.get("direction_confidence"),
            "min_direction_confidence": low_vol.get("resolved_min_direction_confidence"),
            "signal_score": (low_vol.get("score_context") or {}).get("signal_score"),
            "pm_norm_60s": (low_vol.get("price_motion_context") or {}).get("pm_norm_60s"),
            "pm_norm_300s": (low_vol.get("price_motion_context") or {}).get("pm_norm_300s"),
            "spread_bps": (low_vol.get("liquidity_context") or {}).get("spread_bps"),
            "absorption": (low_vol.get("liquidity_context") or {}).get("absorption"),
            "decision_chain_enabled": low_vol.get("decision_chain_enabled"),
            "would_block": low_vol.get("would_block"),
            "block_suppressed_by_config": low_vol.get("block_suppressed_by_config"),
            "violations": ";".join(low_vol.get("violations") or []),
            "mr_regime": mr_bar.mr_regime if mr_bar else None,
            "mr_signal": mr_bar.mr_signal if mr_bar else None,
            "mr_reason": mr_bar.mr_reason if mr_bar else None,
            "pct_b": mr_bar.pct_b if mr_bar else None,
            "rsi": mr_bar.rsi if mr_bar else None,
            **directional,
            "bracket_outcome": bracket.get("outcome") if bracket else None,
            "bracket_gross_bps": bracket.get("gross_bps") if bracket else None,
            "bracket_net_bps": bracket.get("net_bps") if bracket else None,
            "bracket_bars_held": bracket.get("bars_held") if bracket else None,
            "bracket_exit_ts_utc": _iso(bracket.get("exit_ts_ms")) if bracket else None,
        })
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rejected = [r for r in rows if r["event_type"] == "DECISION_INTENT_REJECTED"]
    accepted = [r for r in rows if r["event_type"] == "ORDER_INTENT" and r.get("strategy_id")]
    bracket_rows = [r for r in rejected if r.get("bracket_net_bps") is not None]
    summary: dict[str, Any] = {
        "rows_total": len(rows),
        "accepted_intents": len(accepted),
        "rejected_intents": len(rejected),
        "reject_by_nrr": dict(Counter(r.get("nrr_code") or "UNKNOWN" for r in rejected)),
        "reject_by_symbol": dict(Counter(r.get("symbol") or "UNKNOWN" for r in rejected)),
        "bracket_replay_rows": len(bracket_rows),
        "block_suppressed_by_config": sum(
            1 for r in rejected if str(r.get("block_suppressed_by_config")).lower() == "true"
        ),
    }
    for key in ("nrr_code", "symbol", "side", "mr_signal", "mr_regime"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in bracket_rows:
            groups[str(row.get(key))].append(row)
        summary[f"bracket_by_{key}"] = {
            name: {
                "n": len(items),
                "win_rate": sum(1 for r in items if (r.get("bracket_net_bps") or 0) > 0) / len(items),
                "avg_net_bps": mean(float(r["bracket_net_bps"]) for r in items),
                "median_net_bps": median(float(r["bracket_net_bps"]) for r in items),
                "outcomes": dict(Counter(str(r.get("bracket_outcome")) for r in items)),
            }
            for name, items in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        }
    for horizon in (1, 3, 6, 12):
        field = f"ret_{horizon}bar_bps"
        vals = [float(r[field]) for r in rejected if r.get(field) is not None]
        summary[f"directional_{horizon}bar"] = {
            "n": len(vals),
            "positive_rate": sum(1 for v in vals if v > 0) / len(vals) if vals else None,
            "avg_bps": mean(vals) if vals else None,
            "median_bps": median(vals) if vals else None,
        }
    profitable_blocked = sorted(
        [r for r in bracket_rows if (r.get("bracket_net_bps") or 0) > 0],
        key=lambda r: float(r["bracket_net_bps"]),
        reverse=True,
    )
    losing_blocked = sorted(
        [r for r in bracket_rows if (r.get("bracket_net_bps") or 0) <= 0],
        key=lambda r: float(r["bracket_net_bps"]),
    )
    summary["top_profitable_blocked"] = profitable_blocked[:20]
    summary["top_losing_blocked"] = losing_blocked[:20]
    return summary


def write_outputs(rows: list[dict[str, Any]], summary: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "current_event_gate_replay_rows.csv"
    json_path = out_dir / "current_event_gate_replay_summary.json"
    md_path = out_dir / "CURRENT_EVENT_GATE_REPLAY_REPORT.md"
    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# CURRENT_EVENT_GATE_REPLAY_REPORT",
        "",
        "## Scope",
        "",
        "Read-only replay of current `order_log_v1.jsonl` decisions joined to local 300s mean-reversion bars.",
        "Directional replay uses future 300s closes. Bracket replay is only used when rejected rows carried entry/target/stop geometry.",
        "Net bracket bps subtracts a fixed 10 bps fee+slippage layer.",
        "",
        "## Counts",
        "",
        f"- Rows total: {summary['rows_total']}",
        f"- Accepted intents: {summary['accepted_intents']}",
        f"- Rejected intents: {summary['rejected_intents']}",
        f"- Bracket replay rows: {summary['bracket_replay_rows']}",
        f"- Blocks suppressed by config: {summary['block_suppressed_by_config']}",
        f"- Reject by NRR: {summary['reject_by_nrr']}",
        "",
        "## Directional Follow-Through",
        "",
    ]
    for h in (1, 3, 6, 12):
        s = summary[f"directional_{h}bar"]
        lines.append(
            f"- {h} bars: n={s['n']} positive_rate={s['positive_rate']:.3f} "
            f"avg_bps={s['avg_bps']:.2f} median_bps={s['median_bps']:.2f}"
            if s["positive_rate"] is not None else f"- {h} bars: n=0"
        )
    lines += ["", "## Bracket Replay By NRR", ""]
    for name, s in summary.get("bracket_by_nrr_code", {}).items():
        lines.append(
            f"- {name}: n={s['n']} win_rate={s['win_rate']:.3f} "
            f"avg_net_bps={s['avg_net_bps']:.2f} median_net_bps={s['median_net_bps']:.2f} "
            f"outcomes={s['outcomes']}"
        )
    lines += ["", "## Top Profitable Blocked Bracket Replays", ""]
    for r in summary["top_profitable_blocked"][:10]:
        lines.append(
            f"- {r['ts_utc']} {r['symbol']} {r['side']} {r['nrr_code']} "
            f"net={r['bracket_net_bps']:.2f} outcome={r['bracket_outcome']} "
            f"regime={r['regime']} mr={r['mr_signal']}/{r['mr_regime']} pct_b={r['pct_b']} rid={r['rid']}"
        )
    lines += ["", "## Top Losing Blocked Bracket Replays", ""]
    for r in summary["top_losing_blocked"][:10]:
        lines.append(
            f"- {r['ts_utc']} {r['symbol']} {r['side']} {r['nrr_code']} "
            f"net={r['bracket_net_bps']:.2f} outcome={r['bracket_outcome']} "
            f"regime={r['regime']} mr={r['mr_signal']}/{r['mr_regime']} pct_b={r['pct_b']} rid={r['rid']}"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay current decision gates and policies against local 300s bars."
    )
    parser.add_argument(
        "--window-hours",
        type=float,
        default=None,
        help="Only include events from the last N hours relative to the newest order-log event.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to calibrators/datasets/current_event_gate_replay.",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Write into calibrators/datasets/daily_gate_policy_replay/YYYY-MM-DD.",
    )
    return parser.parse_args()


def _max_order_log_ts_ms() -> int | None:
    max_ts = None
    for _, event in _load_jsonl(LOGS / "order_log_v1.jsonl"):
        ts = event.get("timestamp") or event.get("ts_ms")
        try:
            ts_i = int(ts)
        except (TypeError, ValueError):
            continue
        max_ts = ts_i if max_ts is None else max(max_ts, ts_i)
    return max_ts


def _resolve_out_dir(args: argparse.Namespace, newest_ts_ms: int | None) -> Path:
    if args.out_dir is not None:
        return args.out_dir
    if args.daily:
        if newest_ts_ms is None:
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        else:
            day = datetime.fromtimestamp(
                newest_ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        return ROOT / "calibrators" / "datasets" / "daily_gate_policy_replay" / day
    return OUT_DIR


def main() -> None:
    args = _parse_args()
    newest_ts_ms = _max_order_log_ts_ms()
    since_ms = None
    if args.window_hours is not None:
        if newest_ts_ms is None:
            raise SystemExit("Cannot apply --window-hours: no order-log timestamps found")
        since_ms = int(newest_ts_ms - args.window_hours * 60 * 60 * 1000)
    out_dir = _resolve_out_dir(args, newest_ts_ms)
    bars = load_bars()
    rows = extract_order_events(bars, since_ms=since_ms)
    summary = summarize(rows)
    summary["window_hours"] = args.window_hours
    summary["since_ms"] = since_ms
    summary["newest_ts_ms"] = newest_ts_ms
    write_outputs(rows, summary, out_dir)
    print(json.dumps({
        "out_dir": str(out_dir),
        "window_hours": args.window_hours,
        "since_ms": since_ms,
        "rows": summary["rows_total"],
        "rejected": summary["rejected_intents"],
        "bracket_replay_rows": summary["bracket_replay_rows"],
        "reject_by_nrr": summary["reject_by_nrr"],
        "directional_3bar": summary["directional_3bar"],
    }, indent=2))


if __name__ == "__main__":
    main()
