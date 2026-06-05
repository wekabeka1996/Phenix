#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JOIN_CSV = ROOT / "reports" / \
    "testnet_old_wal_join" / "anchor_trade_join.csv"
DEFAULT_AUDIT_SUMMARY_JSON = ROOT / "reports" / \
    "binance_testnet_window_audit_last7d_utc" / "summary.json"
DEFAULT_OUT_DIR = ROOT / "reports" / "testnet_old_wal_join"


@dataclass
class Bucket:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    flats: int = 0
    net_pnl_sum: float = 0.0
    gross_profit_sum: float = 0.0
    gross_loss_abs_sum: float = 0.0

    def add(self, pnl: float) -> None:
        self.trades += 1
        self.net_pnl_sum += pnl
        if pnl > 0:
            self.wins += 1
            self.gross_profit_sum += pnl
        elif pnl < 0:
            self.losses += 1
            self.gross_loss_abs_sum += abs(pnl)
        else:
            self.flats += 1

    @property
    def loss_rate_pct(self) -> float:
        return (self.losses / self.trades * 100.0) if self.trades else 0.0

    @property
    def win_rate_pct(self) -> float:
        return (self.wins / self.trades * 100.0) if self.trades else 0.0

    @property
    def avg_net_pnl(self) -> float:
        return self.net_pnl_sum / self.trades if self.trades else 0.0

    @property
    def avg_loss_abs(self) -> float:
        return self.gross_loss_abs_sum / self.losses if self.losses else 0.0

    @property
    def avg_win(self) -> float:
        return self.gross_profit_sum / self.wins if self.wins else 0.0

    @property
    def profit_factor(self) -> float | None:
        if self.gross_loss_abs_sum == 0:
            return None if self.gross_profit_sum == 0 else float("inf")
        return self.gross_profit_sum / self.gross_loss_abs_sum


def _safe_float(value: str | None) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _fmt_float(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    if value == float("inf"):
        return "inf"
    return f"{value:.{digits}f}"


def _iter_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        yield from reader


def _load_zero_trade_symbols(path: Path) -> list[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    rows = data.get("symbol_summary")
    if not isinstance(rows, list):
        rows = data.get("per_symbol", [])
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            continue
        orders_total = int(row.get("orders_total") or 0)
        trade_fills = int(row.get("trade_fills") or 0)
        if orders_total == 0 and trade_fills == 0:
            out.append(symbol)
    return sorted(set(out))


def _bucket_to_row(name: str, bucket: Bucket, extra: dict[str, str] | None = None) -> dict[str, str]:
    row = {
        "trades": str(bucket.trades),
        "wins": str(bucket.wins),
        "losses": str(bucket.losses),
        "flats": str(bucket.flats),
        "win_rate_pct": _fmt_float(bucket.win_rate_pct),
        "loss_rate_pct": _fmt_float(bucket.loss_rate_pct),
        "net_pnl_sum": _fmt_float(bucket.net_pnl_sum),
        "avg_net_pnl": _fmt_float(bucket.avg_net_pnl),
        "gross_profit_sum": _fmt_float(bucket.gross_profit_sum),
        "gross_loss_abs_sum": _fmt_float(bucket.gross_loss_abs_sum),
        "avg_win": _fmt_float(bucket.avg_win),
        "avg_loss_abs": _fmt_float(bucket.avg_loss_abs),
        "profit_factor": _fmt_float(bucket.profit_factor, digits=3),
    }
    if extra:
        row.update(extra)
    elif name:
        row["name"] = name
    return row


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _md_table(rows: list[dict[str, str]], columns: list[tuple[str, str]]) -> list[str]:
    header = "| " + " | ".join(label for _, label in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(row.get(key, "") for key, _ in columns) + " |"
        for row in rows
    ]
    return [header, divider, *body]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize anchor trade profitability by symbol and regime.")
    parser.add_argument("--join-csv", type=Path, default=DEFAULT_JOIN_CSV)
    parser.add_argument("--audit-summary-json", type=Path,
                        default=DEFAULT_AUDIT_SUMMARY_JSON)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    rows = list(_iter_rows(args.join_csv))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    total_bucket = Bucket()
    regime_known_bucket = Bucket()
    no_regime_bucket = Bucket()
    symbol_buckets: dict[str, Bucket] = defaultdict(Bucket)
    symbol_regime_buckets: dict[tuple[str, str], Bucket] = defaultdict(Bucket)
    regime_buckets: dict[str, Bucket] = defaultdict(Bucket)
    symbol_regime_known_counts: dict[str, int] = defaultdict(int)
    symbol_regime_unknown_counts: dict[str, int] = defaultdict(int)

    for row in rows:
        symbol = (row.get("symbol") or "").strip()
        regime = (row.get("open_regime") or "").strip()
        pnl = _safe_float(row.get("net_pnl_after_trade_fees_sum"))

        total_bucket.add(pnl)
        if symbol:
            symbol_buckets[symbol].add(pnl)

        if regime:
            regime_known_bucket.add(pnl)
            regime_buckets[regime].add(pnl)
            symbol_regime_buckets[(symbol, regime)].add(pnl)
            symbol_regime_known_counts[symbol] += 1
        else:
            no_regime_bucket.add(pnl)
            symbol_regime_unknown_counts[symbol] += 1

    zero_trade_symbols = [
        symbol for symbol in _load_zero_trade_symbols(args.audit_summary_json)
        if symbol not in symbol_buckets
    ]

    symbol_rows: list[dict[str, str]] = []
    for symbol, bucket in sorted(symbol_buckets.items(), key=lambda item: (item[1].net_pnl_sum, item[0])):
        symbol_rows.append(
            _bucket_to_row(
                symbol,
                bucket,
                extra={
                    "symbol": symbol,
                    "regime_known_trades": str(symbol_regime_known_counts.get(symbol, 0)),
                    "regime_unknown_trades": str(symbol_regime_unknown_counts.get(symbol, 0)),
                },
            )
        )
    for symbol in zero_trade_symbols:
        symbol_rows.append(
            _bucket_to_row(
                symbol,
                Bucket(),
                extra={
                    "symbol": symbol,
                    "regime_known_trades": "0",
                    "regime_unknown_trades": "0",
                },
            )
        )

    regime_rows: list[dict[str, str]] = []
    for regime, bucket in sorted(regime_buckets.items(), key=lambda item: (item[1].net_pnl_sum, item[0])):
        regime_rows.append(_bucket_to_row(
            regime, bucket, extra={"regime": regime}))

    symbol_regime_rows: list[dict[str, str]] = []
    for (symbol, regime), bucket in sorted(symbol_regime_buckets.items(), key=lambda item: (item[0][0], item[1].net_pnl_sum, item[0][1])):
        symbol_regime_rows.append(
            _bucket_to_row(
                f"{symbol}::{regime}",
                bucket,
                extra={
                    "symbol": symbol,
                    "regime": regime,
                },
            )
        )

    symbol_fieldnames = [
        "symbol",
        "trades",
        "wins",
        "losses",
        "flats",
        "win_rate_pct",
        "loss_rate_pct",
        "net_pnl_sum",
        "avg_net_pnl",
        "gross_profit_sum",
        "gross_loss_abs_sum",
        "avg_win",
        "avg_loss_abs",
        "profit_factor",
        "regime_known_trades",
        "regime_unknown_trades",
    ]
    regime_fieldnames = [
        "regime",
        "trades",
        "wins",
        "losses",
        "flats",
        "win_rate_pct",
        "loss_rate_pct",
        "net_pnl_sum",
        "avg_net_pnl",
        "gross_profit_sum",
        "gross_loss_abs_sum",
        "avg_win",
        "avg_loss_abs",
        "profit_factor",
    ]
    symbol_regime_fieldnames = [
        "symbol",
        "regime",
        "trades",
        "wins",
        "losses",
        "flats",
        "win_rate_pct",
        "loss_rate_pct",
        "net_pnl_sum",
        "avg_net_pnl",
        "gross_profit_sum",
        "gross_loss_abs_sum",
        "avg_win",
        "avg_loss_abs",
        "profit_factor",
    ]

    out_symbol_csv = args.out_dir / "profitability_by_symbol.csv"
    out_regime_csv = args.out_dir / "profitability_by_regime.csv"
    out_symbol_regime_csv = args.out_dir / "profitability_by_symbol_and_regime.csv"
    out_md = args.out_dir / "profitability_by_symbol_and_regime.md"
    out_json = args.out_dir / "profitability_by_symbol_and_regime.json"

    _write_csv(out_symbol_csv, symbol_rows, symbol_fieldnames)
    _write_csv(out_regime_csv, regime_rows, regime_fieldnames)
    _write_csv(out_symbol_regime_csv, symbol_regime_rows,
               symbol_regime_fieldnames)

    summary_payload = {
        "source_join_csv": str(args.join_csv),
        "source_audit_summary_json": str(args.audit_summary_json) if args.audit_summary_json.exists() else "",
        "total_anchor_groups": total_bucket.trades,
        "groups_with_open_regime": regime_known_bucket.trades,
        "groups_without_open_regime": no_regime_bucket.trades,
        "regime_coverage_pct": round((regime_known_bucket.trades / total_bucket.trades * 100.0), 2) if total_bucket.trades else 0.0,
        "net_pnl_total": round(total_bucket.net_pnl_sum, 8),
        "net_pnl_with_open_regime": round(regime_known_bucket.net_pnl_sum, 8),
        "net_pnl_without_open_regime": round(no_regime_bucket.net_pnl_sum, 8),
        "gross_abs_pnl_total": round(total_bucket.gross_profit_sum + total_bucket.gross_loss_abs_sum, 8),
        "gross_abs_pnl_with_open_regime": round(regime_known_bucket.gross_profit_sum + regime_known_bucket.gross_loss_abs_sum, 8),
        "zero_trade_symbols_from_audit": zero_trade_symbols,
        "worst_symbol_by_net_pnl": symbol_rows[0]["symbol"] if symbol_rows else "",
        "worst_regime_by_net_pnl": regime_rows[0]["regime"] if regime_rows else "",
        "symbol_rows": symbol_rows,
        "regime_rows": regime_rows,
        "symbol_regime_rows": symbol_regime_rows,
    }
    out_json.write_text(json.dumps(
        summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines: list[str] = []
    md_lines.append("# Anchor Trade Profitability Summary")
    md_lines.append("")
    md_lines.append("## Scope")
    md_lines.append(f"- Source join CSV: {args.join_csv}")
    if args.audit_summary_json.exists():
        md_lines.append(f"- Source audit summary: {args.audit_summary_json}")
    md_lines.append(f"- Total anchor groups: {total_bucket.trades}")
    md_lines.append(
        f"- Groups with recovered open regime: {regime_known_bucket.trades} / {total_bucket.trades} ({_fmt_float(regime_known_bucket.trades / total_bucket.trades * 100.0 if total_bucket.trades else 0.0)}%)"
    )
    md_lines.append(
        f"- Groups without recovered open regime: {no_regime_bucket.trades}")
    md_lines.append(
        f"- Net PnL across all anchor groups: {_fmt_float(total_bucket.net_pnl_sum)}")
    md_lines.append(
        f"- Net PnL covered by regime analysis: {_fmt_float(regime_known_bucket.net_pnl_sum)}")
    md_lines.append(
        f"- Net PnL excluded from regime analysis: {_fmt_float(no_regime_bucket.net_pnl_sum)}")
    gross_abs_total = total_bucket.gross_profit_sum + total_bucket.gross_loss_abs_sum
    gross_abs_known = regime_known_bucket.gross_profit_sum + \
        regime_known_bucket.gross_loss_abs_sum
    coverage_abs_pct = gross_abs_known / \
        gross_abs_total * 100.0 if gross_abs_total else 0.0
    md_lines.append(
        f"- Absolute PnL coverage of regime analysis: {_fmt_float(coverage_abs_pct)}%")
    if zero_trade_symbols:
        md_lines.append(
            f"- Zero-trade symbols in audit summary but absent from closed-trade join: {', '.join(zero_trade_symbols)}")
    md_lines.append("")
    md_lines.append("## Key Findings")
    if symbol_rows:
        worst_symbol = min((row for row in symbol_rows if int(
            row["trades"]) > 0), key=lambda row: float(row["net_pnl_sum"]))
        highest_loss_symbol = max((row for row in symbol_rows if int(
            row["trades"]) > 0), key=lambda row: float(row["loss_rate_pct"]))
        md_lines.append(
            f"- Worst symbol by net PnL: {worst_symbol['symbol']} ({worst_symbol['net_pnl_sum']}, loss rate {worst_symbol['loss_rate_pct']}%, trades {worst_symbol['trades']})."
        )
        md_lines.append(
            f"- Highest symbol loss rate: {highest_loss_symbol['symbol']} ({highest_loss_symbol['loss_rate_pct']}%, net PnL {highest_loss_symbol['net_pnl_sum']}, trades {highest_loss_symbol['trades']})."
        )
    if regime_rows:
        worst_regime = min(
            regime_rows, key=lambda row: float(row["net_pnl_sum"]))
        highest_loss_regime = max(
            regime_rows, key=lambda row: float(row["loss_rate_pct"]))
        md_lines.append(
            f"- Worst open regime overall by net PnL: {worst_regime['regime']} ({worst_regime['net_pnl_sum']}, loss rate {worst_regime['loss_rate_pct']}%, trades {worst_regime['trades']})."
        )
        md_lines.append(
            f"- Highest open regime loss rate: {highest_loss_regime['regime']} ({highest_loss_regime['loss_rate_pct']}%, net PnL {highest_loss_regime['net_pnl_sum']}, trades {highest_loss_regime['trades']})."
        )
    md_lines.append("")
    md_lines.append("## By Symbol")
    md_lines.extend(
        _md_table(
            symbol_rows,
            [
                ("symbol", "Symbol"),
                ("trades", "Trades"),
                ("wins", "Wins"),
                ("losses", "Losses"),
                ("loss_rate_pct", "Loss %"),
                ("net_pnl_sum", "Net PnL"),
                ("avg_net_pnl", "Avg PnL"),
                ("profit_factor", "PF"),
                ("regime_known_trades", "Regime-known"),
                ("regime_unknown_trades", "Regime-unknown"),
            ],
        )
    )
    md_lines.append("")
    md_lines.append("## By Open Regime")
    md_lines.extend(
        _md_table(
            regime_rows,
            [
                ("regime", "Regime"),
                ("trades", "Trades"),
                ("wins", "Wins"),
                ("losses", "Losses"),
                ("loss_rate_pct", "Loss %"),
                ("net_pnl_sum", "Net PnL"),
                ("avg_net_pnl", "Avg PnL"),
                ("profit_factor", "PF"),
            ],
        )
    )
    md_lines.append("")
    md_lines.append("## By Symbol And Open Regime")
    md_lines.extend(
        _md_table(
            symbol_regime_rows,
            [
                ("symbol", "Symbol"),
                ("regime", "Regime"),
                ("trades", "Trades"),
                ("wins", "Wins"),
                ("losses", "Losses"),
                ("loss_rate_pct", "Loss %"),
                ("net_pnl_sum", "Net PnL"),
                ("avg_net_pnl", "Avg PnL"),
                ("profit_factor", "PF"),
            ],
        )
    )
    md_lines.append("")
    md_lines.append("## Notes")
    md_lines.append(
        "- Symbol-level summary uses all anchor groups because symbol and audit net PnL exist even for unmatched WAL groups.")
    md_lines.append(
        "- Regime summaries use only rows with non-empty open_regime, so 9 anchor groups are excluded from regime attribution.")
    md_lines.append(
        "- Net PnL uses net_pnl_after_trade_fees_sum from the join artifact, which is audit-side economics rather than WAL-side partial close evidence.")
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"total_anchor_groups={total_bucket.trades}")
    print(f"groups_with_open_regime={regime_known_bucket.trades}")
    print(f"groups_without_open_regime={no_regime_bucket.trades}")
    print(f"out_symbol_csv={out_symbol_csv}")
    print(f"out_regime_csv={out_regime_csv}")
    print(f"out_symbol_regime_csv={out_symbol_regime_csv}")
    print(f"out_md={out_md}")
    print(f"out_json={out_json}")


if __name__ == "__main__":
    main()
