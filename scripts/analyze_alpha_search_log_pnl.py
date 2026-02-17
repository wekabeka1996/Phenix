#!/usr/bin/env python3
"""Analyze alpha_search domain log and extract PnL stats by symbol.

Input log format (one per line):
  2026-02-16 14:03:03 | INFO | {"event":"VIRTUAL_CLOSE", ... "symbol":"SOLUSDT", "pnl": -3.8744}

We aggregate only events where:
- event == "VIRTUAL_CLOSE"
- symbol is present
- pnl is numeric

Outputs a Markdown summary with per-symbol totals and win rates.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


@dataclass
class PnlAgg:
    closes: int = 0
    wins: int = 0
    losses: int = 0
    flats: int = 0
    pnl_sum: float = 0.0
    gross_profit: float = 0.0
    gross_loss_abs: float = 0.0

    def add(self, pnl: float) -> None:
        self.closes += 1
        self.pnl_sum += pnl
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        elif pnl < 0:
            self.losses += 1
            self.gross_loss_abs += abs(pnl)
        else:
            self.flats += 1

    def win_rate_ex_flats(self) -> float:
        denom = self.wins + self.losses
        return (self.wins / denom) if denom else float("nan")

    def win_rate_all(self) -> float:
        return (self.wins / self.closes) if self.closes else float("nan")

    def avg_pnl(self) -> float:
        return (self.pnl_sum / self.closes) if self.closes else float("nan")

    def profit_factor(self) -> float:
        return (self.gross_profit / self.gross_loss_abs) if self.gross_loss_abs else float("inf")


def _extract_json_payload(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line:
        return None

    # Robust extraction: take substring starting from the first '{'.
    start = line.find("{")
    if start < 0:
        return None

    payload_str = line[start:]
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            parsed = float(value)
        except ValueError:
            return None
        if math.isnan(parsed) or math.isinf(parsed):
            return None
        return parsed
    return None


def iter_virtual_closes(log_path: Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            payload = _extract_json_payload(line)
            if not payload:
                continue
            if payload.get("event") != "VIRTUAL_CLOSE":
                continue
            yield line_no, payload


def render_md_report(
    *,
    log_path: Path,
    out_path: Path,
    totals: PnlAgg,
    per_symbol: Dict[str, PnlAgg],
    parsed_lines: int,
    matched_events: int,
    bad_events: int,
) -> None:
    def fmt_float(x: float, digits: int = 4) -> str:
        if math.isnan(x):
            return "n/a"
        if math.isinf(x):
            return "inf"
        return f"{x:.{digits}f}"

    def fmt_pct(x: float, digits: int = 2) -> str:
        if math.isnan(x):
            return "n/a"
        return f"{100.0 * x:.{digits}f}%"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    rows = sorted(per_symbol.items(),
                  key=lambda kv: kv[1].pnl_sum, reverse=True)

    lines: list[str] = []
    lines.append("# Alpha Search — PnL summary (from logs)")
    lines.append("")
    lines.append(f"- Generated (UTC): {now}")
    lines.append(f"- Log: {log_path.as_posix()}")
    lines.append(f"- Event filter: VIRTUAL_CLOSE")
    lines.append(f"- Parsed lines: {parsed_lines}")
    lines.append(f"- Matched events: {matched_events}")
    lines.append(
        f"- Bad events skipped (missing/invalid symbol or pnl): {bad_events}")
    lines.append("")

    lines.append("## Overall")
    lines.append("")
    lines.append(
        f"- Closes: {totals.closes} (W/L/F = {totals.wins}/{totals.losses}/{totals.flats})")
    lines.append(
        f"- Win rate (ex flats): {fmt_pct(totals.win_rate_ex_flats())}")
    lines.append(f"- Win rate (all): {fmt_pct(totals.win_rate_all())}")
    lines.append(f"- Total PnL: {fmt_float(totals.pnl_sum)}")
    lines.append(f"- Gross profit: {fmt_float(totals.gross_profit)}")
    lines.append(f"- Gross loss (abs): {fmt_float(totals.gross_loss_abs)}")
    lines.append(
        f"- Profit factor: {fmt_float(totals.profit_factor(), digits=3)}")
    lines.append("")

    lines.append("## By symbol")
    lines.append("")
    lines.append(
        "| symbol | closes | wins | losses | flats | win% (ex flats) | win% (all) | pnl_sum | avg_pnl | gross_profit | gross_loss_abs |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")

    for symbol, agg in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    symbol,
                    str(agg.closes),
                    str(agg.wins),
                    str(agg.losses),
                    str(agg.flats),
                    fmt_pct(agg.win_rate_ex_flats()),
                    fmt_pct(agg.win_rate_all()),
                    fmt_float(agg.pnl_sum),
                    fmt_float(agg.avg_pnl()),
                    fmt_float(agg.gross_profit),
                    fmt_float(agg.gross_loss_abs),
                ]
            )
            + " |"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse logs/domain_alpha_search.log and compute PnL + winrate per symbol (from VIRTUAL_CLOSE events)."
    )
    parser.add_argument(
        "--log",
        default=str(Path("logs") / "domain_alpha_search.log"),
        help="Path to domain_alpha_search log file (default: logs/domain_alpha_search.log)",
    )
    parser.add_argument(
        "--out",
        default=str(Path("reports") / "alpha_search_pnl_summary.md"),
        help="Output Markdown path (default: reports/alpha_search_pnl_summary.md)",
    )

    args = parser.parse_args()

    log_path = Path(args.log)
    out_path = Path(args.out)

    if not log_path.exists():
        raise SystemExit(f"Log file not found: {log_path}")

    per_symbol: Dict[str, PnlAgg] = defaultdict(PnlAgg)
    totals = PnlAgg()

    parsed_lines = 0
    matched_events = 0
    bad_events = 0

    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parsed_lines += 1
            payload = _extract_json_payload(line)
            if not payload:
                continue
            if payload.get("event") != "VIRTUAL_CLOSE":
                continue

            matched_events += 1
            symbol = payload.get("symbol")
            pnl = _safe_float(payload.get("pnl"))

            if not isinstance(symbol, str) or not symbol.strip() or pnl is None:
                bad_events += 1
                continue

            symbol = symbol.strip()
            per_symbol[symbol].add(pnl)
            totals.add(pnl)

    render_md_report(
        log_path=log_path,
        out_path=out_path,
        totals=totals,
        per_symbol=dict(per_symbol),
        parsed_lines=parsed_lines,
        matched_events=matched_events,
        bad_events=bad_events,
    )

    print(f"Wrote: {out_path}")
    print(
        f"Events: {matched_events} VIRTUAL_CLOSE (bad skipped: {bad_events})")
    print(f"Symbols: {len(per_symbol)}")
    print(f"Total PnL: {totals.pnl_sum:.4f}")
    print(
        f"Win rate (ex flats): {0.0 if math.isnan(totals.win_rate_ex_flats()) else 100.0*totals.win_rate_ex_flats():.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
