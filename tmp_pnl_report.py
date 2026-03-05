#!/usr/bin/env python3
"""Extract PnL per scenario from alpha_search session logs."""
import json
from pathlib import Path

SESS = Path("logs/alpha_search_runtime/20260304_010258")
log_dir = SESS / "aggregate"

all_shutdowns = []
all_closes = []

# Scan all rotated log files
for logf in sorted(log_dir.glob("domain_alpha_search.log*")):
    with open(logf, encoding="utf-8", errors="ignore") as f:
        for line in f:
            start = line.find("{")
            if start < 0:
                continue
            try:
                d = json.loads(line[start:])
                ev = d.get("event")
                if ev == "SHUTDOWN_SUMMARY":
                    all_shutdowns.append(d)
                elif ev == "VIRTUAL_CLOSE":
                    all_closes.append(d)
            except Exception:
                pass

print(f"SHUTDOWN_SUMMARY records: {len(all_shutdowns)}")
print(f"VIRTUAL_CLOSE records:    {len(all_closes)}")
print()

# Match shutdowns to scenario order (they fire in worker stop order)
SCENARIO_ORDER = [
    "S01_AURORA_BASELINE",
    "S03_AURORA_CONSERVATIVE",
    "S05_AURORA_MY_BEST",
    "S06_AURORA_LOW_THRESHOLD",
    "S20_AURORA_OBI_VERY_HEAVY",
    "S11_MR_BASELINE",
    "S12_MR_RSI_25_75",
    "S13_MR_BB_HEAVY",
    "S15_ENSEMBLE_BALANCED",
    "S18_ENSEMBLE_MOMENTUM_AGGRESSIVE",
    "S19_ENSEMBLE_MR_SHORT_BIAS",
    "S21_ENSEMBLE_REGIME_ADAPTIVE",
]

print("=" * 110)
print("SCENARIO PnL RANKING  (virtual shadow book — 84,534 bars, 5-symbol universe)")
print("=" * 110)
print(f"{'#':<3} {'Scenario':<40} {'TotalPnL':>9} {'Aurora PnL':>11} {'AuroraWR':>9} {'TA PnL':>9} {'TA WR':>7} {'Trades':>7}")
print("-" * 110)

rows = []
for i, s in enumerate(all_shutdowns):
    sid = SCENARIO_ORDER[i] if i < len(SCENARIO_ORDER) else f"S?_{i}"
    pnl = s.get("total_virtual_pnl", 0)
    pp = s.get("per_provider", {})
    aurora = pp.get("aurora", {})
    ta = pp.get("ta_ensemble", {})
    trades = aurora.get("trades_closed", 0) + ta.get("trades_closed", 0)
    combined_wr = (
        (aurora.get("win_rate", 0) * aurora.get("trades_closed", 0) +
         ta.get("win_rate", 0) * ta.get("trades_closed", 0)) /
        trades if trades else 0
    )
    rows.append({
        "rank": i + 1,
        "sid": sid,
        "pnl": pnl,
        "aurora_pnl": aurora.get("pnl", 0),
        "aurora_wr": aurora.get("win_rate", 0),
        "ta_pnl": ta.get("pnl", 0),
        "ta_wr": ta.get("win_rate", 0),
        "trades": trades,
        "combined_wr": combined_wr,
    })

# Sort by total PnL descending
rows.sort(key=lambda x: x["pnl"], reverse=True)

for rank, r in enumerate(rows, 1):
    arrow = " ★" if rank == 1 else ("  ↓" if rank == len(rows) else "")
    print(
        f"{rank:<3} {r['sid']:<40} {r['pnl']:>+9.2f} "
        f"{r['aurora_pnl']:>+11.2f} {r['aurora_wr']:>8.2%} "
        f"{r['ta_pnl']:>+9.2f} {r['ta_wr']:>6.2%} "
        f"{r['trades']:>7,}{arrow}"
    )

print()
best = rows[0]
worst = rows[-1]

# Max DD from VIRTUAL_CLOSE per scenario (approximate)
# Group closes by scenario order
print("=" * 110)
print("KEY METRICS")
print("=" * 110)
print(
    f"  BEST  PnL: {best['sid']:<40}  {best['pnl']:>+8.2f} USDT  WR={best['combined_wr']:.2%}")
print(
    f"  WORST PnL: {worst['sid']:<40} {worst['pnl']:>+8.2f} USDT  WR={worst['combined_wr']:.2%}")
print()

# PnL breakdown
aurora_total = sum(r["aurora_pnl"] for r in rows)
ta_total = sum(r["ta_pnl"] for r in rows)
print(f"  Aurora provider total (12 scenarios): {aurora_total:>+10.2f} USDT")
print(f"  TA Ensemble total  (12 scenarios):    {ta_total:>+10.2f} USDT")
print()

# Approximate drawdown from VIRTUAL_CLOSE events
losses = [c["pnl"] for c in all_closes if c["pnl"] < 0]
wins = [c["pnl"] for c in all_closes if c["pnl"] > 0]
avg_win = sum(wins) / len(wins) if wins else 0
avg_loss = sum(losses) / len(losses) if losses else 0
rr = abs(avg_win / avg_loss) if avg_loss else 0

# Cumulative curve for max DD
equity = []
cum = 0.0
for c in sorted(all_closes, key=lambda x: x.get("ts", 0)):
    cum += c["pnl"]
    equity.append(cum)

max_equity = equity[0] if equity else 0
max_dd = 0.0
for e in equity:
    if e > max_equity:
        max_equity = e
    dd = max_equity - e
    if dd > max_dd:
        max_dd = dd

print(f"  Virtual closes analyzed:  {len(all_closes)}")
print(f"  Win trades:               {len(wins)}  avg={avg_win:>+.4f} USDT")
print(f"  Loss trades:              {len(losses)} avg={avg_loss:>+.4f} USDT")
print(f"  Risk/Reward ratio:        {rr:.2f}")
print(
    f"  Max Drawdown (aggregate): {max_dd:>+.2f} USDT  (combined all scenarios)")
print()
print("NOTE: PnL = virtual shadow book, unit per position (not sized). No fees applied.")
print("      bars_held capped at max_bars=12 per config.")
