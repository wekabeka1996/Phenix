"""
V5 Scenario Matrix Analysis
============================
Reads per-scenario scores.jsonl + prices from alpha_input_v1.jsonl
Simulates virtual trader: entry on BUY/SELL signal, exit after max_bars=12
Computes: PnL, Win Rate, Max Drawdown, Sharpe, avg bars held, signal count
"""
import json
import math
import pathlib
from collections import defaultdict

SESSION = "20260304_144101"
SESSION_DIR = pathlib.Path(f"logs/alpha_search_runtime/{SESSION}")
ALPHA_INPUT = pathlib.Path("logs/alpha_input/alpha_input_v1.jsonl")

NOTIONAL = 1000.0
MAX_BARS = 12
FEE_RATE = 0.0004  # 0.04% per side

# ─── 1. Build price lookup: (symbol, ts_ms) -> price ───────────────────────
print("Loading price index from alpha_input_v1.jsonl ...")
price_index: dict[tuple, float] = {}
with open(ALPHA_INPUT) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            price_index[(r["symbol"], int(r["ts_ms"]))] = float(r["price"])
        except Exception:
            pass
print(f"  Price index: {len(price_index):,} entries")

# ─── 2. Per-scenario analysis ───────────────────────────────────────────────
results = {}

for scenario_dir in sorted(SESSION_DIR.iterdir()):
    if not scenario_dir.is_dir() or scenario_dir.name == "aggregate":
        continue
    scores_file = scenario_dir / "scores.jsonl"
    if not scores_file.exists():
        continue

    sid = scenario_dir.name
    provider_pnl: dict[str, list[float]] = defaultdict(list)
    provider_trades: dict[str, int] = defaultdict(int)
    provider_wins:   dict[str, int] = defaultdict(int)
    provider_bars:   dict[str, list[int]] = defaultdict(list)

    # Virtual positions: provider_id -> {symbol -> open position}
    positions: dict[str, dict[str, dict]] = defaultdict(dict)

    rows_by_symbol_provider: dict[tuple, list] = defaultdict(list)

    # Collect all rows grouped by (symbol, provider_id)
    total_scores = 0
    with open(scores_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            total_scores += 1
            key = (r.get("symbol"), r.get("provider_id"))
            rows_by_symbol_provider[key].append(r)

    # Simulate virtual trader per (symbol, provider_id)
    for (symbol, provider_id), rows in rows_by_symbol_provider.items():
        rows.sort(key=lambda x: x.get("ts_ms", 0))

        pos = None  # {side, entry_price, entry_ts_ms, entry_bar_idx}
        bar_counter = 0

        for i, r in enumerate(rows):
            ts_ms = int(r.get("ts_ms", 0))
            side = r.get("side", "NEUTRAL")
            price = price_index.get((symbol, ts_ms))
            if price is None or price <= 0:
                continue

            bar_counter += 1

            # ── Check exit conditions ────────────────────────────────────
            if pos is not None:
                bars_held = bar_counter - pos["entry_bar"]
                pnl_raw = 0.0
                exit_triggered = False

                if bars_held >= MAX_BARS:
                    # max_bars exit
                    if pos["side"] == "BUY":
                        pnl_raw = (price - pos["entry_price"]) / \
                            pos["entry_price"] * NOTIONAL
                    else:
                        pnl_raw = (pos["entry_price"] - price) / \
                            pos["entry_price"] * NOTIONAL
                    exit_triggered = True

                elif side != "NEUTRAL" and side != pos["side"]:
                    # Signal flip — immediate exit + reverse would be next entry
                    if pos["side"] == "BUY":
                        pnl_raw = (price - pos["entry_price"]) / \
                            pos["entry_price"] * NOTIONAL
                    else:
                        pnl_raw = (pos["entry_price"] - price) / \
                            pos["entry_price"] * NOTIONAL
                    exit_triggered = True

                if exit_triggered:
                    fee = price * NOTIONAL / price * FEE_RATE * 2  # ~= NOTIONAL * FEE_RATE * 2
                    net = pnl_raw - fee
                    provider_pnl[provider_id].append(net)
                    provider_trades[provider_id] += 1
                    if net > 0:
                        provider_wins[provider_id] += 1
                    provider_bars[provider_id].append(bars_held)
                    pos = None

            # ── Check entry ──────────────────────────────────────────────
            if pos is None and side in ("BUY", "SELL"):
                pos = {
                    "side": side,
                    "entry_price": price,
                    "entry_bar": bar_counter,
                }

    # ── Aggregate across providers ───────────────────────────────────────
    all_pnl: list[float] = []
    all_wins = 0
    all_trades = 0
    all_bars: list[int] = []

    for pid in set(list(provider_pnl.keys()) + list(provider_trades.keys())):
        pnls = provider_pnl[pid]
        all_pnl.extend(pnls)
        all_trades += provider_trades[pid]
        all_wins += provider_wins[pid]
        all_bars.extend(provider_bars[pid])

    # PnL stats
    total_pnl = sum(all_pnl)
    win_rate = (all_wins / all_trades * 100) if all_trades > 0 else 0.0
    avg_bars = (sum(all_bars) / len(all_bars)) if all_bars else 0.0

    # Max Drawdown
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in all_pnl:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    # Sharpe (daily-ish, simplified)
    if len(all_pnl) >= 2:
        mean = total_pnl / len(all_pnl)
        var = sum((x - mean) ** 2 for x in all_pnl) / len(all_pnl)
        std = math.sqrt(var) if var > 0 else 0.0
        sharpe = (mean / std * math.sqrt(len(all_pnl))) if std > 0 else 0.0
    else:
        sharpe = 0.0

    results[sid] = {
        "total_pnl":   total_pnl,
        "trades":      all_trades,
        "win_rate":    win_rate,
        "wins":        all_wins,
        "losses":      all_trades - all_wins,
        "max_dd":      max_dd,
        "sharpe":      sharpe,
        "avg_bars":    avg_bars,
        "total_scores": total_scores,
        "fee_cost":    all_trades * NOTIONAL * FEE_RATE * 2,
        "raw_pnl":     total_pnl + all_trades * NOTIONAL * FEE_RATE * 2,
    }
    print(f"  {sid}: {total_scores:,} scores → {all_trades} trades")

# ─── 3. Print report ────────────────────────────────────────────────────────
print()
print("=" * 105)
print(
    f"  V5 SCENARIO ANALYSIS  |  Session {SESSION}  |  Notional={NOTIONAL} USDT  |  Fee={FEE_RATE*100:.3f}%/side")
print("=" * 105)
print(f"{'#':<3} {'Scenario':<42} {'RawPnL':>8} {'NetPnL':>8} {'Trades':>6} {'WR%':>5} {'DD':>7} {'Sharpe':>7} {'AvgBars':>7}")
print("-" * 105)

sorted_r = sorted(
    results.items(), key=lambda x: x[1]["total_pnl"], reverse=True)
for rank, (sid, r) in enumerate(sorted_r, 1):
    marker = "★" if rank == 1 else ("↓" if rank == len(sorted_r) else "")
    print(
        f"{rank:<3} {sid:<42} "
        f"{r['raw_pnl']:>+8.2f} "
        f"{r['total_pnl']:>+8.2f} "
        f"{r['trades']:>6} "
        f"{r['win_rate']:>5.1f} "
        f"{r['max_dd']:>7.2f} "
        f"{r['sharpe']:>7.3f} "
        f"{r['avg_bars']:>7.1f}  {marker}"
    )

print("=" * 105)
best = sorted_r[0][1]
worst = sorted_r[-1][1]

print(f"\n  BEST  net : {sorted_r[0][0]:<42} {best['total_pnl']:>+.2f} USDT")
print(f"  WORST net : {sorted_r[-1][0]:<42} {worst['total_pnl']:>+.2f} USDT")

# Provider breakdown for top 3
print()
print("  Top-3 сценарії — breakdown по провайдерах:")
for sid, r in sorted_r[:3]:
    scores_file = SESSION_DIR / sid / "scores.jsonl"
    aurora_scores = ta_scores = 0
    aurora_buy = aurora_sell = ta_buy = ta_sell = 0
    with open(scores_file) as f:
        for line in f:
            try:
                row = json.loads(line.strip())
            except Exception:
                continue
            s = row.get("side", "")
            if row.get("provider_id") == "aurora":
                aurora_scores += 1
                if s == "BUY":
                    aurora_buy += 1
                elif s == "SELL":
                    aurora_sell += 1
            elif row.get("provider_id") == "ta_ensemble":
                ta_scores += 1
                if s == "BUY":
                    ta_buy += 1
                elif s == "SELL":
                    ta_sell += 1
    print(f"  {sid}:")
    print(
        f"    aurora:    {aurora_scores:>6} scores  BUY={aurora_buy} SELL={aurora_sell}")
    print(f"    ta_ens:    {ta_scores:>6} scores  BUY={ta_buy} SELL={ta_sell}")

# Fee breakeven
print()
if sorted_r[0][1]['trades'] > 0:
    best_raw_per_trade = sorted_r[0][1]['raw_pnl'] / sorted_r[0][1]['trades']
    breakeven_notional = best_raw_per_trade / \
        (FEE_RATE * 2) if best_raw_per_trade > 0 else float('inf')
    print(
        f"  Best scenario avg raw edge/trade : {best_raw_per_trade:+.4f} USDT")
    print(
        f"  Breakeven notional (best)        : {breakeven_notional:.0f} USDT  (current={NOTIONAL:.0f})")
print()
