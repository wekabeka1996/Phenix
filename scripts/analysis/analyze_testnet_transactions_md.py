#!/usr/bin/env python3
"""Analyze a Binance Futures TESTNET transaction Markdown report.

Input is expected to be the output of:
  scripts/fetch_binance_testnet_transactions_md.py

Outputs:
- Prints a concise summary to stdout
- Optionally writes a Markdown summary report

This script intentionally does NOT read API keys.
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _parse_utc_ts(s: str) -> Optional[dt.datetime]:
    s = (s or "").strip()
    if not s:
        return None
    # Expected format: YYYY-MM-DD HH:MM:SS UTC
    if s.endswith("UTC"):
        s = s[:-3].strip()
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _to_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def _md_table_to_rows(lines: List[str], start_idx: int) -> Tuple[List[str], List[List[str]], int]:
    """Parse a GitHub-style markdown table.

    Returns: (headers, rows, next_index_after_table)
    """
    headers_line = lines[start_idx].strip()
    sep_line = lines[start_idx + 1].strip() if start_idx + \
        1 < len(lines) else ""

    def split_row(line: str) -> List[str]:
        # Trim leading/trailing pipe; then split on pipes.
        core = line.strip().strip("|")
        return [c.strip().replace("\\|", "|") for c in core.split("|")]

    headers = split_row(headers_line)
    # quick sanity: separator should be like | --- | --- |
    if "---" not in sep_line:
        raise ValueError("Not a markdown table separator line")

    rows: List[List[str]] = []
    i = start_idx + 2
    while i < len(lines):
        line = lines[i]
        if not line.strip().startswith("|"):
            break
        if "---" in line and line.strip().replace("|", "").strip().startswith("---"):
            i += 1
            continue
        row = split_row(line)
        # tolerate ragged rows
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))
        if len(row) > len(headers):
            row = row[: len(headers)]
        rows.append(row)
        i += 1
    return headers, rows, i


@dataclass
class IncomeRow:
    ts: Optional[dt.datetime]
    asset: str
    income_type: str
    income: float
    symbol: str
    tran_id: str
    info: str


@dataclass
class TradeRow:
    ts: Optional[dt.datetime]
    symbol: str
    side: str
    qty: float
    price: float
    realized_pnl: float
    commission: float
    commission_asset: str
    order_id: str
    trade_id: str


def _extract_tables(md_path: Path) -> Tuple[List[IncomeRow], List[TradeRow], Dict[str, str]]:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    meta: Dict[str, str] = {}
    for line in lines[:40]:
        if line.startswith("Base URL:"):
            meta["base_url"] = line.split(":", 1)[1].strip().strip("`")
        if line.startswith("Range:"):
            meta["range"] = line.split(":", 1)[1].strip()
        if line.startswith("Generated:"):
            meta["generated"] = line.split(":", 1)[1].strip()

    incomes: List[IncomeRow] = []
    trades: List[TradeRow] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("| ") and "incomeType" in line and "tranId" in line:
            headers, rows, nxt = _md_table_to_rows(lines, i)
            idx = {h: n for n, h in enumerate(headers)}
            for r in rows:
                ts = _parse_utc_ts(r[idx.get("time", 0)])
                asset = r[idx.get("asset", 1)]
                income_type = r[idx.get("incomeType", 2)]
                income = _to_float(r[idx.get("income", 3)]) or 0.0
                symbol = r[idx.get("symbol", 4)]
                tran_id = r[idx.get("tranId", 5)]
                info = r[idx.get("info", 6)]
                incomes.append(IncomeRow(ts, asset, income_type,
                               income, symbol, tran_id, info))
            i = nxt
            continue

        if line.startswith("| ") and "realizedPnl" in line and "commissionAsset" in line:
            headers, rows, nxt = _md_table_to_rows(lines, i)
            idx = {h: n for n, h in enumerate(headers)}
            for r in rows:
                ts = _parse_utc_ts(r[idx.get("time", 0)])
                symbol = r[idx.get("symbol", 1)]
                side = r[idx.get("side", 2)]
                qty = _to_float(r[idx.get("qty", 3)]) or 0.0
                price = _to_float(r[idx.get("price", 4)]) or 0.0
                realized_pnl = _to_float(r[idx.get("realizedPnl", 5)]) or 0.0
                commission = _to_float(r[idx.get("commission", 6)]) or 0.0
                commission_asset = r[idx.get("commissionAsset", 7)]
                order_id = r[idx.get("orderId", 8)]
                trade_id = r[idx.get("tradeId", 9)]
                trades.append(
                    TradeRow(ts, symbol, side, qty, price, realized_pnl,
                             commission, commission_asset, order_id, trade_id)
                )
            i = nxt
            continue

        i += 1

    return incomes, trades, meta


def _sum_by_key(items: Iterable[Any], key_fn, value_fn) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for it in items:
        k = str(key_fn(it))
        out[k] = out.get(k, 0.0) + float(value_fn(it))
    return out


def _count_by_key(items: Iterable[Any], key_fn) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for it in items:
        k = str(key_fn(it))
        out[k] = out.get(k, 0) + 1
    return out


def _fmt_money(x: float) -> str:
    return f"{x:.8f}".rstrip("0").rstrip(".") if abs(x) < 1000 else f"{x:.2f}"


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _hour_bucket(ts: Optional[dt.datetime]) -> Optional[int]:
    if ts is None:
        return None
    return int(ts.hour)


def _md_table(headers: List[str], rows: List[List[str]]) -> str:
    """Render a fixed-width (monospace) table for stable column alignment.

    Markdown pipe tables often look misaligned depending on viewer/fonts.
    We intentionally render ASCII tables inside a fenced code block.
    """

    if not headers:
        return "(empty table)\n"

    col_count = len(headers)

    normalized_rows: List[List[str]] = []
    for r in rows:
        r = list(r)
        if len(r) < col_count:
            r = r + [""] * (col_count - len(r))
        if len(r) > col_count:
            r = r[:col_count]
        normalized_rows.append([str(c) for c in r])

    # Widths: max of header/cells, with small minimums to avoid jitter.
    widths: List[int] = []
    for i, h in enumerate(headers):
        max_len = len(str(h))
        for r in normalized_rows:
            max_len = max(max_len, len(r[i]))
        min_w = 10 if i == 0 else 8
        widths.append(max(min_w, max_len))

    # Align: first column left, the rest right.
    right_align = [False] + [True] * (col_count - 1)

    def pad(s: str, w: int, align_right: bool) -> str:
        s = (s or "")
        if len(s) > w:
            s = s[:w]
        return s.rjust(w) if align_right else s.ljust(w)

    hline = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    out: List[str] = []
    out.append("```")
    out.append(hline)
    out.append(
        "| "
        + " | ".join(
            pad(str(h), widths[i], right_align[i]) for i, h in enumerate(headers)
        )
        + " |"
    )
    out.append(hline)
    for r in normalized_rows:
        out.append(
            "| "
            + " | ".join(
                pad(r[i], widths[i], right_align[i]) for i in range(col_count)
            )
            + " |"
        )
    out.append(hline)
    out.append("```")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp",
                    default="reports/testnet_transactions_7d.md", help="Input markdown report")
    ap.add_argument("--out", dest="out", default="reports/testnet_transactions_7d_summary.md",
                    help="Output markdown summary")
    ap.add_argument("--no-write", action="store_true",
                    help="Only print to stdout")
    args = ap.parse_args()

    md_path = Path(args.inp)
    if not md_path.exists():
        raise SystemExit(f"Input markdown not found: {md_path}")

    incomes, trades, meta = _extract_tables(md_path)

    # Coverage
    income_ts = [x.ts for x in incomes if x.ts is not None]
    trade_ts = [x.ts for x in trades if x.ts is not None]
    min_ts = min(income_ts + trade_ts) if (income_ts or trade_ts) else None
    max_ts = max(income_ts + trade_ts) if (income_ts or trade_ts) else None

    # Income summary
    income_total = sum(x.income for x in incomes)
    income_by_type = _sum_by_key(
        incomes, lambda r: r.income_type, lambda r: r.income)
    income_by_symbol = _sum_by_key(
        incomes, lambda r: r.symbol or "(none)", lambda r: r.income)

    # Trade summary
    realized_total = sum(t.realized_pnl for t in trades)
    commission_total = sum(t.commission for t in trades)
    net_total = realized_total - commission_total

    wins = [t for t in trades if t.realized_pnl > 0]
    losses = [t for t in trades if t.realized_pnl < 0]
    flats = [t for t in trades if t.realized_pnl == 0]

    win_count = len(wins)
    loss_count = len(losses)
    flat_count = len(flats)
    denom_wr = (win_count + loss_count)
    win_rate = (win_count / denom_wr) if denom_wr > 0 else 0.0
    win_rate_all = (win_count / len(trades)) if trades else 0.0

    gross_profit = sum(t.realized_pnl for t in wins)
    gross_loss = sum(t.realized_pnl for t in losses)  # negative
    gross_loss_abs = abs(gross_loss)
    profit_factor = (
        gross_profit / gross_loss_abs) if gross_loss_abs > 0 else float("inf")

    avg_win = (gross_profit / win_count) if win_count > 0 else 0.0
    avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0.0

    # Per-trade net after commission (only safe when commissionAsset is USDT)
    net_trade_supported = all(
        (t.commission_asset or "").upper() in ("USDT", "") for t in trades)

    def _trade_net(t: TradeRow) -> float:
        return float(t.realized_pnl) - float(t.commission)

    net_wins: List[TradeRow] = []
    net_losses: List[TradeRow] = []
    net_flats: List[TradeRow] = []
    if net_trade_supported:
        for t in trades:
            n = _trade_net(t)
            if n > 0:
                net_wins.append(t)
            elif n < 0:
                net_losses.append(t)
            else:
                net_flats.append(t)

    # Profitability by symbol
    symbols = sorted({(t.symbol or "(none)") for t in trades})
    per_symbol: Dict[str, Dict[str, float]] = {}
    for sym in symbols:
        tsym = [t for t in trades if (t.symbol or "(none)") == sym]
        per_symbol[sym] = {
            "count": float(len(tsym)),
            "realized": float(sum(t.realized_pnl for t in tsym)),
            "commission": float(sum(t.commission for t in tsym)),
            "net": float(sum((t.realized_pnl - t.commission) for t in tsym)) if net_trade_supported else 0.0,
            "gross_profit": float(sum(t.realized_pnl for t in tsym if t.realized_pnl > 0)),
            "gross_loss_abs": float(abs(sum(t.realized_pnl for t in tsym if t.realized_pnl < 0))),
        }

    # Profitability by hour-of-day (UTC) per symbol
    per_hour_symbol: Dict[Tuple[int, str], Dict[str, float]] = {}
    for t in trades:
        h = _hour_bucket(t.ts)
        if h is None:
            continue
        sym = (t.symbol or "(none)")
        key = (h, sym)
        if key not in per_hour_symbol:
            per_hour_symbol[key] = {
                "count": 0.0,
                "realized": 0.0,
                "commission": 0.0,
                "net": 0.0,
                "wins": 0.0,
                "losses": 0.0,
                "flats": 0.0,
            }
        bucket = per_hour_symbol[key]
        bucket["count"] += 1.0
        bucket["realized"] += float(t.realized_pnl)
        bucket["commission"] += float(t.commission)
        if net_trade_supported:
            bucket["net"] += float(t.realized_pnl) - float(t.commission)
        if t.realized_pnl > 0:
            bucket["wins"] += 1.0
        elif t.realized_pnl < 0:
            bucket["losses"] += 1.0
        else:
            bucket["flats"] += 1.0

    # Best/worst by symbol (using net if supported else realized)
    if per_symbol:
        metric_key = "net" if net_trade_supported else "realized"
        best_sym = max(per_symbol.items(),
                       key=lambda kv: kv[1].get(metric_key, 0.0))[0]
        worst_sym = min(per_symbol.items(),
                        key=lambda kv: kv[1].get(metric_key, 0.0))[0]
    else:
        best_sym = ""
        worst_sym = ""

    # Best/worst hour by net (or realized if net unsupported), aggregated across symbols
    hour_metric_key = "net" if net_trade_supported else "realized"
    per_hour_total: Dict[int, Dict[str, float]] = {
        h: {"metric": 0.0} for h in range(24)}
    for (h, _sym), b in per_hour_symbol.items():
        per_hour_total[h]["metric"] += float(b.get(hour_metric_key, 0.0))
    best_hour = max(per_hour_total.items(), key=lambda kv: kv[1].get(
        "metric", 0.0))[0] if trades else None
    worst_hour = min(per_hour_total.items(), key=lambda kv: kv[1].get(
        "metric", 0.0))[0] if trades else None

    trades_by_symbol = _count_by_key(trades, lambda t: t.symbol or "(none)")
    trades_by_side = _count_by_key(trades, lambda t: t.side or "(none)")
    commission_assets = _count_by_key(
        trades, lambda t: t.commission_asset or "(none)")

    # Sanity checks
    duplicate_trade_ids = len(
        trades) - len({t.trade_id for t in trades if t.trade_id})
    duplicate_tran_ids = len(incomes) - \
        len({i.tran_id for i in incomes if i.tran_id})

    # Print
    print("=== TESTNET TRANSACTIONS SUMMARY ===")
    if meta.get("base_url"):
        print(f"Base URL: {meta['base_url']}")
    if meta.get("range"):
        print(f"Range: {meta['range']}")
    if min_ts and max_ts:
        print(f"Observed time coverage: {min_ts} UTC -> {max_ts} UTC")
    print(f"Income rows: {len(incomes)} | Total income: {income_total}")
    print(
        f"Trades rows: {len(trades)} | RealizedPnL: {realized_total} | Commission: {commission_total} | Net: {net_total}")
    print(f"Wins: {win_count} | Losses: {loss_count} | Flats: {flat_count}")
    print(
        f"Win rate (excl flats): {win_rate:.4f} | Win rate (all trades): {win_rate_all:.4f}")
    print(
        f"Gross profit: {gross_profit} | Gross loss: {gross_loss} | Profit factor: {profit_factor}")
    if net_trade_supported:
        print(
            f"Net-after-commission wins: {len(net_wins)} | losses: {len(net_losses)} | flats: {len(net_flats)}")
    if best_sym or worst_sym:
        print(
            f"Best symbol ({'net' if net_trade_supported else 'realized'}): {best_sym} | Worst: {worst_sym}")
    if best_hour is not None and worst_hour is not None:
        print(
            f"Best UTC hour ({hour_metric_key}): {best_hour:02d}:00 | Worst: {worst_hour:02d}:00")
    print(f"Trades by symbol: {trades_by_symbol}")
    print(f"Trades by side: {trades_by_side}")
    print(f"Commission assets: {commission_assets}")
    if duplicate_tran_ids:
        print(f"WARN: duplicate income tranIds: {duplicate_tran_ids}")
    if duplicate_trade_ids:
        print(f"WARN: duplicate tradeIds: {duplicate_trade_ids}")

    # Build markdown
    md: List[str] = []
    md.append("# Testnet Transactions — Summary\n")
    md.append(f"Input: `{md_path.as_posix()}`\n")
    if meta.get("generated"):
        md.append(f"Input generated: `{meta['generated']}`\n")
    if meta.get("base_url"):
        md.append(f"Base URL: `{meta['base_url']}`\n")
    if meta.get("range"):
        md.append(f"Range: {meta['range']}\n")
    if min_ts and max_ts:
        md.append(
            f"Observed time coverage: `{min_ts.strftime('%Y-%m-%d %H:%M:%S')} UTC` → `{max_ts.strftime('%Y-%m-%d %H:%M:%S')} UTC`\n")

    md.append("## Totals\n")
    md.append(
        f"- Income rows: **{len(incomes)}**, total: **{_fmt_money(income_total)}**\n")
    md.append(f"- Trade rows: **{len(trades)}**\n")
    md.append(f"- Realized PnL (sum): **{_fmt_money(realized_total)}**\n")
    md.append(f"- Commission (sum): **{_fmt_money(commission_total)}**\n")
    md.append(f"- Net (realized - commission): **{_fmt_money(net_total)}**\n")

    md.append("\n## Win Rate & PnL Split (realizedPnl)\n")
    md.append("- `Flat` = trade with `realizedPnl == 0` (break-even by realized PnL; commission may still make net negative).\n")
    md.append(
        f"- Wins: **{win_count}**, Losses: **{loss_count}**, Flats: **{flat_count}**\n")
    md.append(f"- Win rate (excluding flats): **{win_rate * 100:.2f}%**\n")
    md.append(f"- Win rate (all trades): **{win_rate_all * 100:.2f}%**\n")
    md.append(
        f"- Gross profit (sum of positive realizedPnl): **{_fmt_money(gross_profit)}**\n")
    md.append(
        f"- Gross loss (sum of negative realizedPnl): **{_fmt_money(gross_loss)}**\n")
    md.append(f"- Gross loss (abs): **{_fmt_money(gross_loss_abs)}**\n")
    md.append(
        f"- Profit factor (gross_profit / abs(gross_loss)): **{profit_factor:.4f}**\n")
    md.append(
        f"- Avg win: **{_fmt_money(avg_win)}**, Avg loss: **{_fmt_money(avg_loss)}**\n")

    if net_trade_supported:
        net_wr_denom = (len(net_wins) + len(net_losses))
        net_wr = (len(net_wins) / net_wr_denom) if net_wr_denom > 0 else 0.0
        md.append("\n## Net After Commission (USDT)\n")
        md.append(
            f"- Wins: **{len(net_wins)}**, Losses: **{len(net_losses)}**, Flats: **{len(net_flats)}**\n")
        md.append(f"- Win rate (excluding flats): **{_pct(net_wr)}**\n")
    else:
        md.append("\n## Net After Commission\n")
        md.append(
            "(Skipped: commissionAsset is not consistently USDT, so per-trade net comparison may be misleading.)\n")

    md.append("\n## Profitability By Symbol\n")
    if per_symbol:
        metric_key = "net" if net_trade_supported else "realized"
        rows_sym: List[List[str]] = []
        for sym, agg in sorted(per_symbol.items(), key=lambda kv: kv[1].get(metric_key, 0.0), reverse=True):
            rows_sym.append(
                [
                    sym,
                    str(int(agg.get("count", 0.0))),
                    _fmt_money(agg.get("realized", 0.0)),
                    _fmt_money(agg.get("commission", 0.0)),
                    _fmt_money(agg.get("net", 0.0)
                               ) if net_trade_supported else "(n/a)",
                    _fmt_money(agg.get("gross_profit", 0.0)),
                    _fmt_money(agg.get("gross_loss_abs", 0.0)),
                ]
            )
        md.append(
            _md_table(
                ["symbol", "trades", "realized_sum", "commission_sum",
                    "net_sum", "gross_profit", "gross_loss_abs"],
                rows_sym,
            )
        )
        md.append(f"\nBest symbol: **{best_sym}**\n")
        md.append(f"Worst symbol: **{worst_sym}**\n")
    else:
        md.append("(no trades rows)\n")

    md.append("\n## Profitability By UTC Hour\n")
    if trades:
        rows_hr_sym: List[List[str]] = []
        for h in range(24):
            for sym in symbols:
                b = per_hour_symbol.get((h, sym))
                if not b:
                    continue
                cnt = int(b.get("count", 0.0))
                if cnt == 0:
                    continue
                wins_h = int(b.get("wins", 0.0))
                losses_h = int(b.get("losses", 0.0))
                flats_h = int(b.get("flats", 0.0))
                denom = wins_h + losses_h
                wr_h = (wins_h / denom) if denom > 0 else 0.0
                rows_hr_sym.append(
                    [
                        f"{h:02d}:00",
                        sym,
                        str(cnt),
                        _fmt_money(b.get("realized", 0.0)),
                        _fmt_money(b.get("commission", 0.0)),
                        _fmt_money(b.get("net", 0.0)
                                   ) if net_trade_supported else "(n/a)",
                        f"{wins_h}/{losses_h}/{flats_h}",
                        _pct(wr_h),
                    ]
                )

        md.append(
            _md_table(
                [
                    "hour(UTC)",
                    "symbol",
                    "trades",
                    "realized_sum",
                    "commission_sum",
                    "net_sum",
                    "W/L/F",
                    "win_rate(excl F)",
                ],
                rows_hr_sym,
            )
        )
        metric_key = "net" if net_trade_supported else "realized"
        if best_hour is not None and worst_hour is not None:
            md.append(
                f"\nBest UTC hour ({metric_key}, total): **{best_hour:02d}:00**\n")
            md.append(
                f"Worst UTC hour ({metric_key}, total): **{worst_hour:02d}:00**\n")
    else:
        md.append("(no trades rows)\n")

    md.append("\n## Income Breakdown\n")
    rows = [[k, _fmt_money(v), str(_count_by_key([x for x in incomes if x.income_type == k], lambda _: "x").get(
        "x", 0))] for k, v in sorted(income_by_type.items(), key=lambda kv: kv[0])]
    md.append(_md_table(["incomeType", "sum", "count"],
              rows) if rows else "(no income rows)\n")

    md.append("\n## Income By Symbol\n")
    rows = [[k, _fmt_money(v)] for k, v in sorted(
        income_by_symbol.items(), key=lambda kv: -abs(kv[1]))]
    md.append(_md_table(["symbol", "sum"], rows)
              if rows else "(no income rows)\n")

    md.append("\n## Trades Breakdown\n")
    md.append(_md_table(["symbol", "count"], [[s, str(c)] for s, c in sorted(
        trades_by_symbol.items(), key=lambda kv: -kv[1])]) if trades_by_symbol else "(no trades rows)\n")
    md.append("\n")
    md.append(_md_table(["side", "count"], [[s, str(c)] for s, c in sorted(
        trades_by_side.items(), key=lambda kv: -kv[1])]) if trades_by_side else "")

    md.append("\n## Sanity Checks\n")
    md.append(f"- Duplicate income tranIds: **{duplicate_tran_ids}**\n")
    md.append(f"- Duplicate tradeIds: **{duplicate_trade_ids}**\n")
    md.append(
        f"- Commission assets observed: `{', '.join(sorted(commission_assets.keys()))}`\n")

    if not args.no_write:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(md), encoding="utf-8")
        print(f"Wrote summary markdown: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
