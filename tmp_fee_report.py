#!/usr/bin/env python3
"""Fee-adjusted PnL ranking per scenario."""
import json
from pathlib import Path

SESS = Path("logs/alpha_search_runtime/20260304_010258/aggregate")
NOTIONAL = 1000.0
FEE_RATE = 0.0004  # 0.04% per side

SCENARIO_ORDER = [
    "S01_AURORA_BASELINE", "S03_AURORA_CONSERVATIVE", "S05_AURORA_MY_BEST",
    "S06_AURORA_LOW_THRESHOLD", "S20_AURORA_OBI_VERY_HEAVY", "S11_MR_BASELINE",
    "S12_MR_RSI_25_75", "S13_MR_BB_HEAVY", "S15_ENSEMBLE_BALANCED",
    "S18_ENSEMBLE_MOMENTUM_AGGRESSIVE", "S19_ENSEMBLE_MR_SHORT_BIAS",
    "S21_ENSEMBLE_REGIME_ADAPTIVE",
]

summaries = []
for lf in sorted(SESS.glob("domain_alpha_search.log*")):
    with open(lf, encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.find("{")
            if s < 0:
                continue
            try:
                d = json.loads(line[s:])
                if d.get("event") == "SHUTDOWN_SUMMARY":
                    summaries.append(d)
            except Exception:
                pass

fee_per_trade = FEE_RATE * 2 * NOTIONAL  # round-trip fee

print("=" * 100)
print(
    f"FEE-ADJUSTED PnL RANKING  |  Fee={FEE_RATE*100:.4f}% per side ({FEE_RATE*2*100:.4f}% RT)")
print(
    f"Notional={NOTIONAL} USDT/trade  |  Fee per round-trip={fee_per_trade:.4f} USDT")
print("=" * 100)
print(f"{'#':<3} {'Scenario':<40} {'RawPnL':>9} {'Trades':>7} {'FeeCost':>9} {'NetPnL':>9} {'Avg$/tr':>8}")
print("-" * 100)

rows = []
for i, s in enumerate(summaries):
    sid = SCENARIO_ORDER[i] if i < len(SCENARIO_ORDER) else f"S?_{i}"
    raw = s.get("total_virtual_pnl", 0)
    pp = s.get("per_provider", {})
    trades = sum(pp.get(p, {}).get("trades_closed", 0)
                 for p in ("aurora", "ta_ensemble"))
    fee_est = trades * fee_per_trade
    net = raw - fee_est
    avg = raw / trades if trades else 0
    rows.append({"sid": sid, "raw": raw, "trades": trades,
                "fee": fee_est, "net": net, "avg": avg})

rows.sort(key=lambda x: x["net"], reverse=True)

for rank, r in enumerate(rows, 1):
    flag = "  ★" if rank == 1 else ("  ↓" if rank == len(rows) else "")
    print(
        f"{rank:<3} {r['sid']:<40} {r['raw']:>+9.2f} {r['trades']:>7,} "
        f"{r['fee']:>+9.2f} {r['net']:>+9.2f} {r['avg']:>+8.4f}{flag}"
    )

print()
best = rows[0]
worst = rows[-1]
s18 = next(r for r in rows if "S18" in r["sid"])
s21 = next(r for r in rows if "S21" in r["sid"])

print("=" * 100)
print("ВИСНОВКИ")
print("=" * 100)
print(f"\n  BEST  net: {best['sid']:<40}  {best['net']:>+.2f} USDT")
print(f"  WORST net: {worst['sid']:<40} {worst['net']:>+.2f} USDT")
print()
print(f"  Fee per RT ({NOTIONAL} USDT notional):  {fee_per_trade:.4f} USDT")
print(f"  S18 avg edge per trade:               {s18['avg']:+.4f} USDT")
print(f"  S21 avg edge per trade:               {s21['avg']:+.4f} USDT")
print(
    f"  Shortfall (S18 edge vs fee):          {s18['avg'] - fee_per_trade:+.4f} USDT/trade")
print()

# Breakeven notional for S18
# net = raw - trades * fee_rate * 2 * notional > 0
# raw / (trades * fee_rate * 2) > notional
# notional_breakeven = raw_per_trade / (fee_rate * 2)
be_notional = s18["avg"] / (FEE_RATE * 2)
print(
    f"  S18 breakeven notional: {be_notional:.0f} USDT  (current={NOTIONAL})")
print()

# Sensitivity
print("-" * 80)
print("  S18 — PnL при різних нот. розмірах та ставках комісії:")
print()
print(f"  {'Notional':>10}  {'Fee%RT':>7}  {'FeeCost':>10}  {'NetPnL':>10}  {'Status'}")
print(f"  {'-'*60}")
for notional in [100, 500, 1000, 2000, 5000, 10000]:
    for fee_rt_pct in [0.04, 0.02, 0.01]:
        fee_rt = fee_rt_pct / 100
        fee_total = s18["trades"] * fee_rt * notional
        raw_scaled = s18["raw"] * (notional / NOTIONAL)
        net_scaled = raw_scaled - fee_total
        status = "✓ PROFIT" if net_scaled > 0 else "✗ LOSS"
        if fee_rt_pct == 0.04:  # only print 0.04 row per notional for brevity
            print(
                f"  {notional:>10}  {fee_rt_pct:>6.2f}%  {fee_total:>+10.2f}  {net_scaled:>+10.2f}  {status}")
print()
print(f"  Full sensitivity (notional=1000, S18):")
print(f"  {'FeeRate%':>10}  {'FeeCost':>10}  {'NetPnL':>10}  {'Status'}")
for fee_rt_pct in [0.04, 0.02, 0.01, 0.005, 0.001, 0.0]:
    fee_rt = fee_rt_pct / 100
    fee_total = s18["trades"] * fee_rt * NOTIONAL * 2
    net = s18["raw"] - fee_total
    status = "✓ PROFIT" if net > 0 else "✗ LOSS"
    print(f"  {fee_rt_pct:>10.3f}%  {fee_total:>+10.2f}  {net:>+10.2f}  {status}")
