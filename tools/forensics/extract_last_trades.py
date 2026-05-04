"""Extract last N *closed* trades (round-trips) into a lifecycle table.

Primary source (authoritative fills):
  - reports/testnet_tx_48h.md (Trades / userTrades table)

Enrichment (best-effort):
  - logs/order_log_v1.jsonl (metadata: regime, signal_score)
  - logs/domain_feature_engineering.log* (Calculated features for SYMBOL: {...})

Output:
  - Markdown table with columns:
      symbol | side | entry_time(UTC) | exit_time(UTC) | duration_sec |
      realized_pnl | commission | signal_score | regime_at_entry |
      main_features (obi,tfi,macro_resid,delta_price)

Notes:
  - Trades are reconstructed per-symbol by simulating position quantity from fills.
  - Partial fills are naturally handled.
  - Flips (sign change without returning to zero) are handled by splitting a fill:
      realizedPnl is attributed to the closing leg; commission is split pro-rata.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


BASE = Path(__file__).resolve().parents[2]


_MD_ROW_RE = re.compile(r"^\|(?P<body>.+)\|\s*$")


def _dt_to_utc_str(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _parse_report_time(s: str) -> datetime:
    # Example: "2026-02-18 18:40:09 UTC"
    return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)


def _parse_feature_log_time(s: str) -> datetime:
    # Example: "2026-02-20 21:51:25,440"
    return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=timezone.utc)


def _safe_float(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def _is_close_to_zero(x: float, *, eps: float = 1e-12) -> bool:
    return abs(x) <= eps


def _sign(x: float, *, eps: float = 1e-12) -> int:
    if x > eps:
        return 1
    if x < -eps:
        return -1
    return 0


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


@dataclass(frozen=True)
class Fill:
    ts: datetime
    symbol: str
    side: str  # BUY/SELL
    qty: float
    price: float
    realized_pnl: float
    commission: float
    order_id: str
    trade_id: str


@dataclass
class Trade:
    symbol: str
    side: str  # entry side: BUY=long, SELL=short
    entry_time: datetime
    exit_time: datetime
    realized_pnl: float
    commission: float
    signal_score: float | None = None
    regime_at_entry: str | None = None
    features: dict[str, float] | None = None

    @property
    def duration_sec(self) -> int:
        return int((self.exit_time - self.entry_time).total_seconds())


def parse_user_trades_from_md(path: Path) -> list[Fill]:
    if not path.exists():
        raise FileNotFoundError(path)

    rows: list[Fill] = []
    found_section = False
    in_table = False
    headers: list[str] | None = None

    with path.open(encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")
            if line.strip() == "## Trades (fapi/v1/userTrades)":
                found_section = True
                in_table = False
                headers = None
                continue

            if found_section and not in_table and line.strip().startswith("| time | symbol | side | qty | price | realizedPnl | commission |"):
                m0 = _MD_ROW_RE.match(line.strip())
                if not m0:
                    continue
                headers = [c.strip() for c in m0.group("body").split("|")]
                in_table = True
                continue

            if not in_table:
                continue

            m = _MD_ROW_RE.match(line.strip())
            if not m:
                # table ended
                if rows:
                    break
                continue

            cols = [c.strip() for c in m.group("body").split("|")]
            if not cols:
                continue

            # separator row
            if all(set(c) <= {"-", ":"} for c in cols):
                continue

            if headers is None:
                # Shouldn't happen if header was parsed; keep it defensive.
                headers = cols
                continue

            if len(cols) != len(headers):
                continue

            rec = dict(zip(headers, cols))
            ts = _parse_report_time(rec["time"])
            symbol = rec["symbol"]
            side = rec["side"].upper()

            qty = _safe_float(rec["qty"])
            price = _safe_float(rec["price"])
            realized_pnl = _safe_float(rec["realizedPnl"])
            commission = _safe_float(rec["commission"])

            rows.append(
                Fill(
                    ts=ts,
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    price=price,
                    realized_pnl=realized_pnl,
                    commission=commission,
                    order_id=str(rec.get("orderId", "")),
                    trade_id=str(rec.get("tradeId", "")),
                )
            )

    # stable order: ts, then trade_id numeric if possible
    def _sort_key(f: Fill):
        try:
            tid = int(f.trade_id)
        except Exception:
            tid = 0
        return (f.ts, tid)

    rows.sort(key=_sort_key)
    return rows


def reconstruct_closed_trades(fills: list[Fill]) -> list[Trade]:
    by_symbol: dict[str, list[Fill]] = {}
    for f in fills:
        by_symbol.setdefault(f.symbol, []).append(f)

    closed: list[Trade] = []

    for symbol, sym_fills in by_symbol.items():
        pos_qty = 0.0
        open_trade: Trade | None = None

        for f in sym_fills:
            signed = f.qty if f.side.upper() == "BUY" else -f.qty
            if _is_close_to_zero(signed):
                continue

            prev_pos = pos_qty
            prev_sign = _sign(prev_pos)

            # Start trade if flat
            if open_trade is None and _is_close_to_zero(prev_pos):
                open_trade = Trade(
                    symbol=symbol,
                    side="BUY" if signed > 0 else "SELL",
                    entry_time=f.ts,
                    exit_time=f.ts,
                    realized_pnl=0.0,
                    commission=0.0,
                )

            # Apply fill into current trade accounting
            if open_trade is not None:
                open_trade.realized_pnl += 0.0 if math.isnan(
                    f.realized_pnl) else f.realized_pnl
                open_trade.commission += 0.0 if math.isnan(
                    f.commission) else f.commission

            pos_qty = prev_pos + signed
            new_sign = _sign(pos_qty)

            # Flip handling: sign change without going flat
            if prev_sign != 0 and new_sign != 0 and prev_sign != new_sign and open_trade is not None:
                qty_to_close = abs(prev_pos)
                qty_fill = abs(signed)
                frac_close = min(1.0, qty_to_close /
                                 qty_fill) if qty_fill > 0 else 1.0

                # Split commission pro-rata; realizedPnl is attributed to the closing leg.
                close_comm = (0.0 if math.isnan(f.commission)
                              else f.commission) * frac_close
                open_comm = (0.0 if math.isnan(f.commission)
                             else f.commission) - close_comm

                # Remove the full commission we already added above; re-add split parts.
                open_trade.commission -= 0.0 if math.isnan(
                    f.commission) else f.commission
                open_trade.commission += close_comm

                open_trade.exit_time = f.ts
                closed.append(open_trade)

                # Start new trade at the same fill timestamp.
                open_trade = Trade(
                    symbol=symbol,
                    side="BUY" if new_sign > 0 else "SELL",
                    entry_time=f.ts,
                    exit_time=f.ts,
                    realized_pnl=0.0,
                    commission=open_comm,
                )

            # Close handling
            if open_trade is not None and _is_close_to_zero(pos_qty):
                open_trade.exit_time = f.ts
                closed.append(open_trade)
                open_trade = None

        # Ignore open trade if still open at end of report

    return closed


def load_orderlog_enrichment(order_log_path: Path) -> dict[str, list[tuple[int, float | None, str | None]]]:
    """Per symbol: list of (ts_ms, signal_score, regime)."""
    per_sym: dict[str, list[tuple[int, float | None, str | None]]] = {}
    if not order_log_path.exists():
        return per_sym

    for ev in _iter_jsonl(order_log_path):
        ts = ev.get("timestamp")
        if not isinstance(ts, (int, float)):
            continue
        ts_ms = int(ts)
        sym = ev.get("symbol")
        if not isinstance(sym, str) or not sym:
            continue
        md = ev.get("metadata") or {}
        if not isinstance(md, dict):
            continue
        if "regime" not in md and "signal_score" not in md:
            continue
        regime = md.get("regime")
        if regime is not None and not isinstance(regime, str):
            regime = str(regime)
        score_raw = md.get("signal_score")
        score = None
        if score_raw is not None:
            try:
                score = float(score_raw)
            except (TypeError, ValueError):
                score = None

        per_sym.setdefault(sym, []).append((ts_ms, score, regime))

    for sym in per_sym:
        per_sym[sym].sort(key=lambda x: x[0])
    return per_sym


def _lookup_latest_before(
    series: list[tuple[int, object, object]],
    target_ms: int,
    *,
    max_lookback_s: int,
) -> tuple[int, object, object] | None:
    """Return last (ts, a, b) with ts <= target_ms and within lookback window."""
    if not series:
        return None
    lo = 0
    hi = len(series) - 1
    idx = None
    while lo <= hi:
        mid = (lo + hi) // 2
        ts = series[mid][0]
        if ts <= target_ms:
            idx = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if idx is None:
        return None
    ts, a, b = series[idx]
    if (target_ms - ts) > max_lookback_s * 1000:
        return None
    return ts, a, b


def load_feature_snapshots(feature_paths: list[Path]) -> dict[str, list[tuple[int, dict[str, float]]]]:
    """Per symbol: list of (ts_ms, features) where features includes at least keys used by output."""
    per_sym: dict[str, list[tuple[int, dict[str, float]]]] = {}
    if not feature_paths:
        return per_sym

    # Example line:
    # 2026-02-20 21:51:25,440 - ... - Calculated features for BTCUSDT: {"obi": "...", ...}
    line_re = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+-\s+.*Calculated features for (?P<sym>[A-Z0-9_]+):\s+(?P<json>\{.*\})\s*$"
    )

    for p in feature_paths:
        if not p.exists():
            continue
        with p.open(encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip("\n")
                m = line_re.match(raw)
                if not m:
                    continue
                try:
                    ts = _parse_feature_log_time(m.group("ts"))
                except ValueError:
                    continue
                sym = m.group("sym")
                try:
                    payload = json.loads(m.group("json"))
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue

                # Keep only requested keys, but parse as float.
                keep: dict[str, float] = {}
                for k in ("obi", "tfi", "macro_resid", "delta_price"):
                    if k in payload:
                        try:
                            keep[k] = float(payload[k])
                        except (TypeError, ValueError):
                            # sometimes strings; fall back to nan
                            keep[k] = float("nan")
                per_sym.setdefault(sym, []).append(
                    (int(ts.timestamp() * 1000), keep))

    for sym in per_sym:
        per_sym[sym].sort(key=lambda x: x[0])
    return per_sym


def _format_features(feats: dict[str, float] | None) -> str:
    if not feats:
        return ""
    parts: list[str] = []
    for k in ("obi", "tfi", "macro_resid", "delta_price"):
        v = feats.get(k)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            parts.append(f"{k}=")
        else:
            parts.append(f"{k}={v:.6g}")
    return "; ".join(parts)


def write_markdown(trades: list[Trade], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write("# Last closed trades\n\n")
        fh.write(
            "| symbol | side | entry_time(UTC) | exit_time(UTC) | duration_sec | realized_pnl | commission | signal_score | regime_at_entry | main_features (obi,tfi,macro_resid,delta_price) |\n"
        )
        fh.write(
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        )
        for t in trades:
            fh.write(
                "| {symbol} | {side} | {entry} | {exit} | {dur} | {pnl:.10g} | {comm:.10g} | {score} | {regime} | {feats} |\n".format(
                    symbol=t.symbol,
                    side=t.side,
                    entry=_dt_to_utc_str(t.entry_time),
                    exit=_dt_to_utc_str(t.exit_time),
                    dur=t.duration_sec,
                    pnl=t.realized_pnl,
                    comm=t.commission,
                    score="" if t.signal_score is None else f"{t.signal_score:.6g}",
                    regime="" if t.regime_at_entry is None else t.regime_at_entry,
                    feats=_format_features(t.features),
                )
            )


def write_csv(trades: list[Trade], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "symbol",
                "side",
                "entry_time_utc",
                "exit_time_utc",
                "duration_sec",
                "realized_pnl",
                "commission",
                "signal_score",
                "regime_at_entry",
                "obi",
                "tfi",
                "macro_resid",
                "delta_price",
            ],
        )
        w.writeheader()
        for t in trades:
            feats = t.features or {}
            w.writerow(
                {
                    "symbol": t.symbol,
                    "side": t.side,
                    "entry_time_utc": _dt_to_utc_str(t.entry_time),
                    "exit_time_utc": _dt_to_utc_str(t.exit_time),
                    "duration_sec": t.duration_sec,
                    "realized_pnl": t.realized_pnl,
                    "commission": t.commission,
                    "signal_score": "" if t.signal_score is None else t.signal_score,
                    "regime_at_entry": "" if t.regime_at_entry is None else t.regime_at_entry,
                    "obi": feats.get("obi", ""),
                    "tfi": feats.get("tfi", ""),
                    "macro_resid": feats.get("macro_resid", ""),
                    "delta_price": feats.get("delta_price", ""),
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tx-report", type=Path, default=BASE /
                    "reports" / "testnet_tx_48h.md")
    ap.add_argument("--order-log", type=Path, default=BASE /
                    "logs" / "order_log_v1.jsonl")
    ap.add_argument(
        "--feature-logs",
        type=str,
        default=str(BASE / "logs" / "domain_feature_engineering.log*"),
        help="Glob for feature engineering logs.",
    )
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out-md", type=Path, default=BASE /
                    "reports" / "last_50_trades.md")
    ap.add_argument("--out-csv", type=Path, default=BASE /
                    "reports" / "last_50_trades.csv")
    ap.add_argument("--no-csv", action="store_true")
    ap.add_argument("--max-orderlog-lookback-s", type=int, default=15 * 60)
    ap.add_argument("--max-feature-lookback-s", type=int, default=5 * 60)
    args = ap.parse_args()

    fills = parse_user_trades_from_md(args.tx_report)
    if not fills:
        print(f"No userTrades parsed from {args.tx_report}", file=sys.stderr)
        return 2

    trades = reconstruct_closed_trades(fills)
    if not trades:
        print("No closed trades reconstructed from fills (position never returned to 0 within report window).", file=sys.stderr)
        return 2

    # Sort by exit time desc; take last N
    trades.sort(key=lambda t: t.exit_time, reverse=True)
    trades = trades[: max(1, args.limit)]

    # ---- enrichment ----
    orderlog = load_orderlog_enrichment(args.order_log)

    feature_paths = [Path(p) for p in sorted(glob.glob(args.feature_logs))]
    features = load_feature_snapshots(feature_paths)

    for t in trades:
        entry_ms = int(t.entry_time.timestamp() * 1000)

        s = orderlog.get(t.symbol)
        if s:
            hit = _lookup_latest_before(
                s, entry_ms, max_lookback_s=args.max_orderlog_lookback_s)
            if hit:
                _ts, score, regime = hit
                if isinstance(score, float):
                    t.signal_score = score
                if isinstance(regime, str) and regime:
                    t.regime_at_entry = regime

        fser = features.get(t.symbol)
        if fser:
            # binary search last <= entry_ms
            lo, hi = 0, len(fser) - 1
            idx = None
            while lo <= hi:
                mid = (lo + hi) // 2
                ts_ms = fser[mid][0]
                if ts_ms <= entry_ms:
                    idx = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            if idx is not None:
                ts_ms, feats = fser[idx]
                if (entry_ms - ts_ms) <= args.max_feature_lookback_s * 1000:
                    t.features = feats

    write_markdown(trades, args.out_md)
    if not args.no_csv:
        write_csv(trades, args.out_csv)

    print(f"Wrote {len(trades)} trades -> {args.out_md}")
    if not args.no_csv:
        print(f"Wrote {len(trades)} trades -> {args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
