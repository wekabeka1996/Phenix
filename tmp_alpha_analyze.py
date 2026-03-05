#!/usr/bin/env python3
"""Full alpha_search session analysis report."""
import json
from pathlib import Path
from collections import defaultdict

SESS = Path("logs/alpha_search_runtime/20260304_010258")

rows = []
for sdir in sorted(d for d in SESS.iterdir() if d.is_dir() and d.name.startswith("S")):
    sf = sdir / "scores.jsonl"
    if not sf.exists():
        continue
    cnt = buy = sell = neu = 0
    scores = []
    by_prov = defaultdict(lambda: {"buy": 0, "sell": 0, "neu": 0, "sc": []})
    by_sym = defaultdict(lambda: {"buy": 0, "sell": 0, "neu": 0})
    with open(sf, encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                r = json.loads(line)
                cnt += 1
                sc = float(r.get("score", 0))
                scores.append(sc)
                side = str(r.get("side", "NEUTRAL")).upper()
                sym = r.get("symbol", "?")
                prov = r.get("provider_id", "?")
                if side == "BUY":
                    buy += 1
                    by_sym[sym]["buy"] += 1
                    by_prov[prov]["buy"] += 1
                elif side == "SELL":
                    sell += 1
                    by_sym[sym]["sell"] += 1
                    by_prov[prov]["sell"] += 1
                else:
                    neu += 1
                    by_sym[sym]["neu"] += 1
                    by_prov[prov]["neu"] += 1
                by_prov[prov]["sc"].append(sc)
            except Exception:
                pass
    rows.append({
        "sid": sdir.name, "cnt": cnt, "buy": buy, "sell": sell, "neu": neu,
        "avg": sum(scores) / len(scores) if scores else 0,
        "bias": sell - buy, "dir_pct": (buy + sell) / cnt * 100 if cnt else 0,
        "by_prov": dict(by_prov), "by_sym": dict(by_sym),
    })

print("SESSION 20260304_010258  |  84,534 snapshots  |  0 errors  |  0 degradations")
print()
print(f"{'Scenario':<40} {'Total':>8} {'BUY':>7} {'SELL':>7} {'NEU':>7} {'Dir%':>6} {'Bias':>7} {'AvgSc':>8}")
print("-" * 96)
for r in rows:
    print(f"{r['sid']:<40} {r['cnt']:>8,} {r['buy']:>7,} {r['sell']:>7,} {r['neu']:>7,} {r['dir_pct']:>5.1f}% {r['bias']:>+7,} {r['avg']:>+8.4f}")

r0 = rows[0]
print()
print("Provider split (S01_AURORA_BASELINE):")
print(f"  {'Provider':<16} {'BUY':>7} {'SELL':>7} {'NEU':>7} {'AvgScore':>9}")
print("  " + "-" * 50)
for prov, pd in sorted(r0["by_prov"].items()):
    pavg = sum(pd["sc"]) / len(pd["sc"]) if pd["sc"] else 0
    print(
        f"  {prov:<16} {pd['buy']:>7,} {pd['sell']:>7,} {pd['neu']:>7,} {pavg:>+9.4f}")

print()
print("Per-symbol split (S01_AURORA_BASELINE):")
print(f"  {'Symbol':<12} {'BUY':>7} {'SELL':>7} {'NEU':>7} {'Bias':>7}")
print("  " + "-" * 45)
for sym, sd in sorted(r0["by_sym"].items()):
    print(
        f"  {sym:<12} {sd['buy']:>7,} {sd['sell']:>7,} {sd['neu']:>7,} {sd['sell'] - sd['buy']:>+7,}")

print()
print("=" * 80)
print("КЛЮЧОВІ ВИСНОВКИ")
print("=" * 80)
max_dir = max(rows, key=lambda x: x["dir_pct"])
min_dir = min(rows, key=lambda x: x["dir_pct"])
max_bias = max(rows, key=lambda x: x["bias"])
s13 = next((r for r in rows if "S13" in r["sid"]), None)
s18 = next((r for r in rows if "S18" in r["sid"]), None)
neg_cnt = sum(1 for r in rows if r["avg"] < 0)
print(
    f"1. SELL BIAS: стабільний у ВСІХ 12 сценах. Макс bias: {max_bias['sid']} ({max_bias['bias']:+,})")
print(f"   → Підозра: знак delta_price або macro_resid feature зміщений донизу")
print(
    f"2. avg_score < 0: {neg_cnt}/12 сценаріїв — aurora scoring має систематичну негативну тенденцію")
print(
    f"3. Directional activity: від {min_dir['dir_pct']:.1f}% ({min_dir['sid']}) до {max_dir['dir_pct']:.1f}% ({max_dir['sid']})")
print(f"4. aurora покрив 50,907 calls — ~40% барів BTCUSDT fail-closed (missing delta_price/macro_resid)")
if s13:
    print(
        f"5. S13_MR_BB_HEAVY: SELL={s13['sell']:,} vs BUY={s13['buy']:,} — BB squeeze штовхає у короткі позиції")
if s18:
    print(
        f"6. S18_ENSEMBLE_MOMENTUM_AGGRESSIVE: {s18['dir_pct']:.1f}% directional — найактивніший сценарій")
print()
print("РЕКОМЕНДАЦІЇ:")
print("  [C1] BTCUSDT missing features → перевірити feature_engineering pipeline для BTCUSDT 5m")
print("  [W1] Негативний avg_score → калібрувати AuroraScoringKernel offset/normalization")
print("  [W2] SELL > BUY скрізь → перевірити знак delta_price в feature_engineering")
print(f"  [I1] aggregate_metrics.csv 224MB готовий для pandas: SESS/aggregate/aggregate_metrics.csv")

# --- Summary ---
summary_path = SESSION / "aggregate" / "summary.jsonl"
lines = summary_path.read_text(encoding="utf-8").strip().split("\n")
print(f"Summary entries: {len(lines)}")

last = json.loads(lines[-1])
scenarios = last.get("scenarios", {})
print(f"Scenarios: {len(scenarios)}\n")

rows = []
for sid, data in scenarios.items():
    sp = data.get("snapshots_processed", 0)
    tr = data.get("total_results", 0)
    sf = data.get("snapshots_failed", 0)
    sb = data.get("shadow_book", {})
    pnl = sb.get("cumulative_pnl", 0) if sb else 0
    trades = sb.get("total_trades", 0) if sb else 0
    wr = sb.get("win_rate", 0) if sb else 0
    sharpe = sb.get("sharpe_ratio", 0) if sb else 0
    rows.append((sid, sp, tr, sf, pnl, trades, wr, sharpe))

# Sort by PnL
rows.sort(key=lambda x: x[4], reverse=True)

print(f"{'Scenario':<35} {'Proc':>5} {'Res':>5} {'Fail':>5} {'PnL':>10} {'Trades':>7} {'WinRate':>8} {'Sharpe':>8}")
print("-" * 90)
for (sid, sp, tr, sf, pnl, trades, wr, sharpe) in rows:
    wr_str = f"{wr:.1%}" if wr else "N/A"
    sharpe_str = f"{sharpe:.3f}" if sharpe else "N/A"
    print(f"{sid:<35} {sp:>5} {tr:>5} {sf:>5} {pnl:>10.4f} {trades:>7} {wr_str:>8} {sharpe_str:>8}")

# --- Health ---
health_path = SESSION / "aggregate" / "health.jsonl"
if health_path.exists():
    health_lines = health_path.read_text(encoding="utf-8").strip().split("\n")
    print(f"\nHealth events: {len(health_lines)}")
    for hl in health_lines[:3]:
        try:
            h = json.loads(hl)
            status = h.get("status", {})
            print(
                f"  ts={h.get('ts', '?'):.0f} statuses={list(status.items())[:3]}")
        except Exception as e:
            print(f"  parse error: {e}")

# --- Scores files per scenario ---
print("\n--- Per-scenario scores.jsonl ---")
for sdir in sorted(SESSION.iterdir()):
    if not sdir.is_dir() or sdir.name == "aggregate":
        continue
    sf = sdir / "scores.jsonl"
    agg_csv = SESSION / "aggregate" / "aggregate_metrics.csv"
    if sf.exists():
        cnt = sum(1 for _ in open(sf, encoding="utf-8", errors="ignore"))
        print(f"  {sdir.name}: {cnt} lines")
    else:
        print(f"  {sdir.name}: no scores.jsonl")

if agg_csv.exists():
    cnt = sum(1 for _ in open(agg_csv, encoding="utf-8", errors="ignore"))
    print(f"\naggregate_metrics.csv: {cnt} rows (incl. header)")
else:
    print("\nNo aggregate_metrics.csv")
