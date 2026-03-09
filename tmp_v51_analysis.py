"""
V5.1 Scenario Matrix Analysis — session 20260305_042428
==========================================================
scores.jsonl format:
  side: BUY | SELL | NEUTRAL   (resolved signal, already threshold-filtered)
  confidence: float            (provider confidence)
  threshold: float
  provider_id, symbol, ts_ms, score, why, regime
"""
import bisect
import json
import math
import pathlib
from collections import defaultdict

SESSION = "20260306_090256"
SESSION_DIR = pathlib.Path(f"logs/alpha_search_runtime/{SESSION}")
ALPHA_INPUT = pathlib.Path("logs/alpha_input/alpha_input_v1.jsonl")

NOTIONAL = 5000.0  # v6: 5000 USDT per trade (was 1000)
MAX_BARS = 12
FEE_RATE = 0.0004   # 0.04%/side

# ── Per-scenario config (flip_on_reversal from scenario_matrix v6) ──────────
# flip=True: close position on opposite signal AND immediately open in new direction
# flip=False: close on max_bars OR opposite signal, then wait for next entry
SCENARIO_CFG: dict[str, dict] = {
    "S01_MR_RSI_HEAVY":                 {"flip": False, "notional": 5000},
    "S03_AURORA_15M_APPROX":            {"flip": False, "notional": 5000},
    "S05_AURORA_MACRO_RESIDUAL":        {"flip": False, "notional": 5000},
    "S06_AURORA_ETH_CALIBRATED":        {"flip": False, "notional": 5000},
    "S11_MR_BASELINE":                  {"flip": False, "notional": 5000},
    "S12_MR_RSI_25_75":                 {"flip": False, "notional": 5000},
    "S13_MR_BB_HEAVY":                  {"flip": False, "notional": 5000},
    "S15_ENSEMBLE_BALANCED":            {"flip": False, "notional": 5000},
    "S18_ENSEMBLE_MOMENTUM_AGGRESSIVE": {"flip": True,  "notional": 5000},
    "S19_ENSEMBLE_MR_SHORT_BIAS":       {"flip": False, "notional": 5000},
    "S20_AURORA_MICROSTRUCTURE_DEPTH":  {"flip": False, "notional": 5000},
    "S21_ENSEMBLE_REGIME_ADAPTIVE":     {"flip": True,  "notional": 5000},
}

# ── 1. Price index ───────────────────────────────────────────────────────────
print("Loading price index …")
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
print(f"  Price index: {len(price_index):,} entries\n")

# ── 2. Nearest price lookup ──────────────────────────────────────────────────
# Sort per-symbol timestamps for bisect
sym_ts: dict[str, list[int]] = defaultdict(list)
sym_price: dict[str, list[float]] = {}
for (sym, ts), px in price_index.items():
    sym_ts[sym].append(ts)
for sym in sym_ts:
    sym_ts[sym].sort()
    sym_price[sym] = [price_index[(sym, t)] for t in sym_ts[sym]]


def nearest_price(sym: str, ts_ms: int) -> float | None:
    ts_list = sym_ts.get(sym)
    if not ts_list:
        return None
    idx = bisect.bisect_left(ts_list, ts_ms)
    if idx == 0:
        return sym_price[sym][0]
    if idx >= len(ts_list):
        return sym_price[sym][-1]
    before = sym_price[sym][idx-1]
    after = sym_price[sym][idx]
    return before if abs(ts_list[idx-1]-ts_ms) <= abs(ts_list[idx]-ts_ms) else after


# ── 3. Per-scenario analysis ─────────────────────────────────────────────────
results = {}

for scenario_dir in sorted(SESSION_DIR.iterdir()):
    if not scenario_dir.is_dir() or scenario_dir.name == "aggregate":
        continue
    scores_file = scenario_dir / "scores.jsonl"
    if not scores_file.exists():
        continue

    sid = scenario_dir.name
    cfg = SCENARIO_CFG.get(sid, {"flip": False, "notional": NOTIONAL})
    scen_flip: bool = bool(cfg["flip"])
    scen_notional: float = float(cfg["notional"])

    rows_by_key: dict[tuple, list] = defaultdict(list)
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
            rows_by_key[key].append(r)

    all_pnl: list[float] = []
    all_trades = 0
    all_wins = 0
    all_bars_held: list[int] = []
    side_counts = {"BUY": 0, "SELL": 0, "NEUTRAL": 0}

    for (symbol, provider_id), rows in rows_by_key.items():
        rows.sort(key=lambda x: x.get("ts_ms", 0))
        pos = None

        for i, r in enumerate(rows):
            ts_ms = int(r.get("ts_ms", 0))
            side = str(r.get("side") or "NEUTRAL").upper()
            conf = float(r.get("confidence", 0) or 0)
            thr = float(r.get("threshold",  0) or 0)

            if side not in side_counts:
                side = "NEUTRAL"
            side_counts[side] += 1

            entry_price = nearest_price(symbol, ts_ms)
            if entry_price is None or entry_price <= 0:
                continue

            just_closed_on_reversal = False  # used by flip=False to block re-open

            # ── Close existing position ───────────────────────────────────────
            if pos is not None:
                bars_held = i - pos["bar_idx"]
                is_reversal = side in ("BUY", "SELL") and side != pos["side"]
                should_close = bars_held >= MAX_BARS or is_reversal

                if should_close:
                    exit_price = entry_price
                    p_notional = pos.get("notional", scen_notional)
                    if pos["side"] == "BUY":
                        raw_pnl = (
                            exit_price - pos["entry_price"]) / pos["entry_price"] * p_notional
                    else:
                        raw_pnl = (pos["entry_price"] - exit_price) / \
                            pos["entry_price"] * p_notional
                    net_pnl = raw_pnl - p_notional * FEE_RATE * 2

                    all_trades += 1
                    all_pnl.append(net_pnl)
                    if net_pnl > 0:
                        all_wins += 1
                    all_bars_held.append(i - pos["bar_idx"])
                    pos = None

                    # flip=False → don't immediately re-open on reversal bar
                    if is_reversal and not scen_flip:
                        just_closed_on_reversal = True

            # ── Open new position (confidence must pass threshold) ────────────
            if (not just_closed_on_reversal
                    and pos is None
                    and side in ("BUY", "SELL")
                    and conf >= thr):
                pos = {"side": side, "entry_price": entry_price,
                       "bar_idx": i, "notional": scen_notional}

    # Metrics
    n = all_trades
    raw_pnl_total = sum(all_pnl)
    avg_pnl = raw_pnl_total / n if n else 0
    win_rate = all_wins / n if n else 0
    avg_bars = sum(all_bars_held) / len(all_bars_held) if all_bars_held else 0

    # Max drawdown
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

    # Sharpe
    if len(all_pnl) > 1:
        mean = avg_pnl
        std = math.sqrt(sum((x - mean)**2 for x in all_pnl) / (n-1))
        sharpe = (mean / std * math.sqrt(n)) if std > 0 else 0
    else:
        sharpe = 0

    results[sid] = {
        "snapshots": total_scores,
        "trades":    n,
        "raw_pnl":   raw_pnl_total,
        "win_rate":  win_rate,
        "avg_bars":  avg_bars,
        "max_dd":    max_dd,
        "sharpe":    sharpe,
        "buy_sig":   side_counts["BUY"],
        "sell_sig":  side_counts["SELL"],
    }

# ── 4. Print ranked results ───────────────────────────────────────────────────
sorted_results = sorted(
    results.items(), key=lambda x: x[1]["raw_pnl"], reverse=True)

print("=" * 115)
print(f"{'#':>2} {'Scenario':<38} {'Snaps':>8} {'Trades':>7} {'Net PnL':>10} {'Win%':>7} "
      f"{'AvgBars':>8} {'MaxDD':>9} {'Sharpe':>7} {'BUY':>7} {'SELL':>7}")
print("=" * 115)

for rank, (sid, m) in enumerate(sorted_results, 1):
    print(
        f"{rank:>2} {sid:<38} "
        f"{m['snapshots']:>8,} "
        f"{m['trades']:>7,} "
        f"{m['raw_pnl']:>+10.2f} "
        f"{m['win_rate']*100:>7.1f}% "
        f"{m['avg_bars']:>8.1f} "
        f"{m['max_dd']:>9.2f} "
        f"{m['sharpe']:>7.3f} "
        f"{m['buy_sig']:>7,} "
        f"{m['sell_sig']:>7,}"
    )

print("=" * 115)

# ── 5. Fee-sensitivity for top-3 ─────────────────────────────────────────────
RT_FEE = NOTIONAL * FEE_RATE * 2
print("\n📊 Fee-sensitivity (Net PnL) — top 3 scenarios:")
print(f"  {'Scenario':<38}  " +
      "  ".join(f"{bps/100:.2f}%/s" for bps in [0, 2, 4, 6, 8, 10]))
for sid, m in sorted_results[:3]:
    raw_gross = m["raw_pnl"] + m["trades"] * RT_FEE  # gross before fees
    row = []
    for bps in [0, 2, 4, 6, 8, 10]:
        adj = raw_gross - m["trades"] * NOTIONAL * (bps/10000) * 2
        row.append(f"{adj:>+9.0f}")
    print(f"  {sid:<38}  " + "  ".join(row))

# ── 6. Group summary ──────────────────────────────────────────────────────────
groups = {
    "Aurora":   [(s, m) for s, m in sorted_results if "AURORA" in s],
    "MR":       [(s, m) for s, m in sorted_results if "MR" in s and "ENSEMBLE" not in s],
    "Ensemble": [(s, m) for s, m in sorted_results if "ENSEMBLE" in s],
}
print("\n📦 Group summary:")
for grp, items in groups.items():
    if not items:
        continue
    pnls = [m["raw_pnl"] for _, m in items]
    trades = [m["trades"] for _, m in items]
    best_s = max(items, key=lambda x: x[1]["raw_pnl"])[0]
    print(f"  {grp:<10}  best={best_s:<38}  avg={sum(pnls)/len(pnls):>+9.2f}  "
          f"best={max(pnls):>+9.2f}  worst={min(pnls):>+9.2f}  avg_trades={sum(trades)/len(trades):>7.0f}")

# ── 7. Aurora differentiation check ─────────────────────────────────────────
aurora_items = groups["Aurora"]
if aurora_items:
    unique_pnl = len(set(round(m["raw_pnl"], 2) for _, m in aurora_items))
    print(
        f"\n🔬 Aurora PnL differentiation: {unique_pnl}/{len(aurora_items)} distinct values")
    for s, m in sorted(aurora_items, key=lambda x: x[1]["raw_pnl"], reverse=True):
        print(f"   {s:<42} trades={m['trades']:>5,}  pnl={m['raw_pnl']:>+9.2f}  "
              f"buy={m['buy_sig']:>6,}  sell={m['sell_sig']:>6,}")

print(f"\n✅ Session: {SESSION}  |  Scenarios: {len(results)}")
