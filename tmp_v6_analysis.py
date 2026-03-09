"""
V6 scenario analysis — session 20260306_090256
Compares with v5.1 baseline, detects duplicates, per-trade quality metrics.
"""
import bisect
import json
import pathlib
import collections
import statistics

SESSION = "20260306_090256"
SESSION_DIR = pathlib.Path(f"logs/alpha_search_runtime/{SESSION}")
PRICE_DIR = pathlib.Path("logs/alpha_input/alpha_input_v1.jsonl")

NOTIONAL = 5000.0
FEE_RATE = 0.0004          # 0.04%/side
MAX_BARS = 12

FLIP_SCENARIOS = {
    "S18_ENSEMBLE_MOMENTUM_AGGRESSIVE",
    "S21_ENSEMBLE_REGIME_ADAPTIVE",
}

# v5.1 reference (1000 USDT notional)
V51_REF = {
    "S12_MR_RSI_25_75":                {"trades": 17328, "gross": 13843, "net": -10420, "win_pct": 30.1},
    "S11_MR_BASELINE":                  {"trades": 18422, "gross": 12049, "net": -11178, "win_pct": 29.8},
    "S01_MR_RSI_HEAVY":                 {"trades": 19278, "gross": 11031, "net": -12162, "win_pct": 30.2},
    "S20_AURORA_MICROSTRUCTURE_DEPTH":  {"trades": 20428, "gross": 12033, "net": -12360, "win_pct": 29.9},
    "S21_ENSEMBLE_REGIME_ADAPTIVE":     {"trades": 20675, "gross": 11029, "net": -12829, "win_pct": 29.9},
    "S06_AURORA_ETH_CALIBRATED":        {"trades": 22187, "gross":  3489, "net": -17511, "win_pct": 20.0},
    "S05_AURORA_MACRO_RESIDUAL":        {"trades": 22511, "gross":  3531, "net": -17802, "win_pct": 19.8},
}


# ── Price index ──────────────────────────────────────────────────────────────

price_by_sym: dict = collections.defaultdict(list)

if PRICE_DIR.exists():
    with open(PRICE_DIR) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            sym = r.get("symbol")
            ts = int(r.get("ts_ms", 0))
            px = float(r.get("close") or r.get("price") or 0)
            if sym and ts and px:
                price_by_sym[sym].append((ts, px))

for sym in price_by_sym:
    price_by_sym[sym].sort()


def nearest_price(symbol, ts_ms):
    lst = price_by_sym.get(symbol)
    if not lst:
        return None
    tss = [x[0] for x in lst]
    idx = bisect.bisect_left(tss, ts_ms)
    if idx >= len(lst):
        idx = len(lst) - 1
    return lst[idx][1]


# ── Per-scenario simulation ──────────────────────────────────────────────────
rows_table = []

for scenario_dir in sorted(SESSION_DIR.iterdir()):
    if not scenario_dir.is_dir() or scenario_dir.name == "aggregate":
        continue
    scores_file = scenario_dir / "scores.jsonl"
    if not scores_file.exists():
        continue

    sid = scenario_dir.name
    flip = sid in FLIP_SCENARIOS

    rows_by_key: dict = collections.defaultdict(list)
    total_scores = 0
    provider_counts: dict = collections.Counter()

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
            rows_by_key[key].append(r)
            provider_counts[r.get("provider_id", "?")] += 1

    all_pnl: list = []
    all_trades = 0
    all_wins = 0
    all_bars_held: list = []
    side_counts: dict = collections.Counter()
    conf_vals: list = []

    for (symbol, provider_id), rows in rows_by_key.items():
        rows.sort(key=lambda x: x.get("ts_ms", 0))
        pos = None

        for i, r in enumerate(rows):
            ts_ms = int(r.get("ts_ms", 0))
            side = str(r.get("side") or "NEUTRAL").upper()
            conf = float(r.get("confidence", 0) or 0)
            thr = float(r.get("threshold",  0) or 0)

            if side not in ("BUY", "SELL", "NEUTRAL"):
                side = "NEUTRAL"
            side_counts[side] += 1
            if side in ("BUY", "SELL"):
                conf_vals.append(conf)

            entry_price = nearest_price(symbol, ts_ms)
            if entry_price is None or entry_price <= 0:
                continue

            just_closed_on_reversal = False

            if pos is not None:
                bars_held = i - pos["bar_idx"]
                is_reversal = side in ("BUY", "SELL") and side != pos["side"]
                should_close = bars_held >= MAX_BARS or is_reversal

                if should_close:
                    exit_p = entry_price
                    if pos["side"] == "BUY":
                        raw_pnl = (exit_p - pos["entry_price"]) / \
                            pos["entry_price"] * NOTIONAL
                    else:
                        raw_pnl = (pos["entry_price"] - exit_p) / \
                            pos["entry_price"] * NOTIONAL
                    net_pnl = raw_pnl - NOTIONAL * FEE_RATE * 2

                    all_trades += 1
                    all_pnl.append(net_pnl)
                    if net_pnl > 0:
                        all_wins += 1
                    all_bars_held.append(i - pos["bar_idx"])
                    pos = None

                    if is_reversal and not flip:
                        just_closed_on_reversal = True

            if (not just_closed_on_reversal
                    and pos is None
                    and side in ("BUY", "SELL")
                    and conf >= thr):
                pos = {"side": side, "entry_price": entry_price, "bar_idx": i}

    n = all_trades
    gross_pnl = sum(p + NOTIONAL * FEE_RATE * 2 for p in all_pnl)
    net_pnl = sum(all_pnl)
    win_rate = all_wins / n if n else 0
    avg_bars = sum(all_bars_held) / len(all_bars_held) if all_bars_held else 0
    avg_conf = statistics.mean(conf_vals) if conf_vals else 0

    peak = 0.0
    max_dd = 0.0
    cum = 0.0
    for p in all_pnl:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    sharpe = 0.0
    if len(all_pnl) > 1:
        std = statistics.stdev(all_pnl)
        if std > 0:
            sharpe = (statistics.mean(all_pnl) / std) * (n ** 0.5)

    # gross per $1k per trade (quality metric)
    gross_per_1k = (gross_pnl / n / NOTIONAL * 1000) if n else 0

    rows_table.append({
        "sid": sid,
        "snaps": total_scores,
        "trades": n,
        "gross": gross_pnl,
        "net": net_pnl,
        "win": win_rate,
        "avg_bars": avg_bars,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "buy": side_counts.get("BUY", 0),
        "sell": side_counts.get("SELL", 0),
        "avg_conf": avg_conf,
        "gross_per_1k": gross_per_1k,
        "flip": flip,
        "providers": dict(provider_counts),
    })

rows_table.sort(key=lambda x: x["net"], reverse=True)

# ── Print ────────────────────────────────────────────────────────────────────
HDR = "  #  Scenario                                Trades   Gross     Net    Win%  AvgBars  MaxDD  Sharpe  G/1k"
SEP = "=" * len(HDR)
print(SEP)
print(HDR)
print(SEP)
for i, r in enumerate(rows_table, 1):
    flip_tag = " [FLIP]" if r["flip"] else ""
    print(f"{i:>3}  {r['sid']:<40}   {r['trades']:>5}  {r['gross']:>+8.0f}  {r['net']:>+8.0f}  "
          f"{r['win']*100:>5.1f}%  {r['avg_bars']:>5.1f}  {r['max_dd']:>7.0f}  {r['sharpe']:>+6.2f}  "
          f"{r['gross_per_1k']:>+.3f}{flip_tag}")
print(SEP)

# ── Duplicate detection ───────────────────────────────────────────────────────
print("\n=== DUPLICATE CHECK (identical net PnL → identical signal stream) ===")
net_groups: dict = collections.defaultdict(list)
for r in rows_table:
    net_groups[round(r["net"], 2)].append(r["sid"])
has_dup = False
for net_val, sids in net_groups.items():
    if len(sids) > 1:
        print(f"  ⚠ DUPLICATE net={net_val:+.2f}  →  {', '.join(sids)}")
        has_dup = True
if not has_dup:
    print("  ✅ No duplicates detected")

# ── v5.1 comparison ───────────────────────────────────────────────────────────
print("\n=== v5.1 → v6 comparison (normalized to $1k notional per trade) ===")
print(f"  {'Scenario':<45} {'v5.1 G/1k':>10} {'v6 G/1k':>10}  {'v5.1 trades':>12} {'v6 trades':>10}")
for r in rows_table:
    ref = V51_REF.get(r["sid"])
    if not ref:
        continue
    v51_gross = ref["net"] + ref["trades"] * 1000 * \
        FEE_RATE * 2   # recover gross from net
    v51_gpk = v51_gross / ref["trades"]  # per trade, 1k notional
    print(f"  {r['sid']:<45} {v51_gpk:>+10.3f} {r['gross_per_1k']:>+10.3f}  {ref['trades']:>12,} {r['trades']:>10,}")

# ── Group summary ──────────────────────────────────────────────────────────────
groups = {
    "MR":       [r for r in rows_table if "MR" in r["sid"] or r["sid"].startswith("S01")],
    "Aurora":   [r for r in rows_table if "AURORA" in r["sid"]],
    "Ensemble": [r for r in rows_table if "ENSEMBLE" in r["sid"]],
}
print("\n=== Group summary ===")
for grp, rs in groups.items():
    if not rs:
        continue
    best = max(rs, key=lambda x: x["net"])
    avg_net = sum(x["net"] for x in rs) / len(rs)
    avg_trd = sum(x["trades"] for x in rs) / len(rs)
    avg_gpk = sum(x["gross_per_1k"] for x in rs) / len(rs)
    print(
        f"  {grp:<10} best={best['sid']:<40}  avg_net={avg_net:>+8.0f}  avg_trades={avg_trd:>6.0f}  avg_G/1k={avg_gpk:>+.3f}")

print(
    f"\n Session: {SESSION}  |  Scenarios: {len(rows_table)}  |  Notional: ${NOTIONAL:.0f}/trade")
