#!/usr/bin/env python3
"""Temporary utility: fee-adjust PnL from domain_alpha_search log.

Goal (per user request):
- Exclude SOL, include BTC & ETH
- Apply commission 0.04% on BOTH open and close (taker-like fee)
- Compute final (net) PnL after fees

We infer trade quantity from the logged virtual close:
- For side=BUY: pnl = (exit_price - entry_price) * qty
- For side=SELL: pnl = (entry_price - exit_price) * qty

Fee model:
- fee_open  = fee_rate * abs(qty * entry_price)
- fee_close = fee_rate * abs(qty * exit_price)
- net_pnl   = pnl - (fee_open + fee_close)

This is a *synthetic* calculation because the log doesn't provide executed qty/notional.
However, in this repo's logs the implied notional is typically ~1000 USDT per trade.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


@dataclass
class FeeAgg:
    closes: int = 0
    raw_pnl_sum: float = 0.0
    fee_sum: float = 0.0
    net_pnl_sum: float = 0.0
    wins: int = 0
    losses: int = 0
    flats: int = 0

    def add(self, raw_pnl: float, fee: float) -> None:
        self.closes += 1
        self.raw_pnl_sum += raw_pnl
        self.fee_sum += fee
        self.net_pnl_sum += (raw_pnl - fee)
        if raw_pnl > 0:
            self.wins += 1
        elif raw_pnl < 0:
            self.losses += 1
        else:
            self.flats += 1


def _extract_json_payload(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line:
        return None
    start = line.find("{")
    if start < 0:
        return None
    try:
        payload = json.loads(line[start:])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            x = float(value)
        except ValueError:
            return None
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    return None


def iter_virtual_close_events(log_path: Path) -> Iterable[Dict[str, Any]]:
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            payload = _extract_json_payload(line)
            if not payload:
                continue
            if payload.get("event") != "VIRTUAL_CLOSE":
                continue
            yield payload


def infer_qty(side: str, entry: float, exit_: float, pnl: float) -> Optional[float]:
    if side == "BUY":
        denom = exit_ - entry
    elif side == "SELL":
        denom = entry - exit_
    else:
        return None

    if denom == 0:
        return None

    qty = pnl / denom
    if qty == 0:
        # If pnl==0 but denom!=0, qty==0 which implies no position. Skip.
        return None

    return abs(qty)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute fee-adjusted PnL from logs/domain_alpha_search.log")
    parser.add_argument(
        "--log", default=str(Path("logs") / "domain_alpha_search.log"))
    parser.add_argument("--fee-rate", type=float, default=0.0004,
                        help="Fee rate per side (default 0.0004 = 0.04%%)")
    parser.add_argument(
        "--include-symbols",
        default="BTCUSDT,ETHUSDT",
        help="Comma-separated symbols to include (default: BTCUSDT,ETHUSDT)",
    )

    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        raise SystemExit(f"Log file not found: {log_path}")

    fee_rate = float(args.fee_rate)
    if fee_rate < 0:
        raise SystemExit("--fee-rate must be >= 0")

    include_symbols = {s.strip() for s in str(
        args.include_symbols).split(",") if s.strip()}
    if not include_symbols:
        raise SystemExit("--include-symbols is empty")

    totals = FeeAgg()
    per_symbol: Dict[str, FeeAgg] = defaultdict(FeeAgg)

    skipped_bad = 0
    skipped_not_included = 0

    for e in iter_virtual_close_events(log_path):
        symbol = e.get("symbol")
        if not isinstance(symbol, str) or symbol.strip() not in include_symbols:
            skipped_not_included += 1
            continue
        symbol = symbol.strip()

        side = e.get("side")
        if not isinstance(side, str):
            skipped_bad += 1
            continue
        side = side.strip().upper()

        entry = _safe_float(e.get("entry_price"))
        exit_ = _safe_float(e.get("exit_price"))
        pnl = _safe_float(e.get("pnl"))
        if entry is None or exit_ is None or pnl is None:
            skipped_bad += 1
            continue

        qty = infer_qty(side=side, entry=entry, exit_=exit_, pnl=pnl)
        if qty is None:
            skipped_bad += 1
            continue

        open_notional = abs(qty * entry)
        close_notional = abs(qty * exit_)
        fee = fee_rate * (open_notional + close_notional)

        totals.add(raw_pnl=pnl, fee=fee)
        per_symbol[symbol].add(raw_pnl=pnl, fee=fee)

    def fmt(x: float) -> str:
        return f"{x:.6f}"

    print(f"Log: {log_path}")
    print(f"Included symbols: {sorted(include_symbols)}")
    print(f"Fee rate per side: {fee_rate} ({fee_rate*100:.4f}%)")
    print(f"Skipped (not included): {skipped_not_included}")
    print(f"Skipped (bad/missing fields): {skipped_bad}")
    print("")

    print("OVERALL")
    print(
        f"  closes: {totals.closes}  (W/L/F raw pnl = {totals.wins}/{totals.losses}/{totals.flats})")
    print(f"  raw_pnl_sum: {fmt(totals.raw_pnl_sum)}")
    print(f"  fee_sum:     {fmt(totals.fee_sum)}")
    print(f"  net_pnl_sum: {fmt(totals.net_pnl_sum)}")
    print("")

    print("BY SYMBOL")
    for symbol in sorted(per_symbol.keys()):
        a = per_symbol[symbol]
        print(
            f"  {symbol}: closes={a.closes} raw={fmt(a.raw_pnl_sum)} fee={fmt(a.fee_sum)} net={fmt(a.net_pnl_sum)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
