import re
import os
from datetime import datetime
from collections import defaultdict

LOG_DIR = r"c:\Users\user\Music\Phenix\logs"

REGIME_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+.*?"
    r"\[(\w+)\] Regime updated: (.+?) \u2192 (\w+) "
    r"\(raw=(\w+), confidence=([\d.]+)"
)

transitions = []

log_files = []
for f in os.listdir(LOG_DIR):
    fpath = os.path.join(LOG_DIR, f)
    if not os.path.isfile(fpath):
        continue
    if f.startswith("aurora_core.log") or f.startswith("domain_regime_detector.log"):
        log_files.append(fpath)

for fpath in sorted(log_files):
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = REGIME_PATTERN.search(line)
                if m:
                    ts_str, symbol, old_regime, new_regime, raw, conf = m.groups()
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    transitions.append({
                        "ts": ts,
                        "symbol": symbol,
                        "old": old_regime.strip(),
                        "new": new_regime,
                        "raw": raw,
                        "confidence": float(conf),
                    })
    except Exception as e:
        print(f"Error reading {fpath}: {e}")

transitions.sort(key=lambda x: x["ts"])

if not transitions:
    print("NO REGIME TRANSITIONS FOUND!")
    exit()

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]

print(f"Total transitions found: {len(transitions)}")
print(f"Date range: {transitions[0]['ts']} -- {transitions[-1]['ts']}")
print()

REGIMES = ["TREND_UP", "TREND_DOWN", "FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH",
           "MEAN_REVERSION", "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNCERTAIN"]

symbol_trans = defaultdict(list)
for t in transitions:
    if t["symbol"] in SYMBOLS:
        symbol_trans[t["symbol"]].append(t)

analysis_end = max(t["ts"] for t in transitions)

results = {}
for sym in SYMBOLS:
    strans = symbol_trans.get(sym, [])
    if not strans:
        results[sym] = None
        continue

    regime_seconds = defaultdict(float)
    regime_durations = []
    total_transitions = 0
    regime_durations_by_type = defaultdict(list)

    for i, t in enumerate(strans):
        start = t["ts"]
        if i + 1 < len(strans):
            end = strans[i + 1]["ts"]
        else:
            end = analysis_end

        duration = (end - start).total_seconds()
        regime_seconds[t["new"]] += duration
        regime_durations.append(duration)
        regime_durations_by_type[t["new"]].append(duration)
        if t["old"] not in ("", "\u2205"):
            total_transitions += 1

    total_seconds = sum(regime_seconds.values())
    hours_covered = total_seconds / 3600

    regime_pct = {}
    for r in REGIMES:
        pct = (regime_seconds.get(r, 0) / total_seconds * 100) if total_seconds > 0 else 0
        regime_pct[r] = pct

    results[sym] = {
        "regime_pct": regime_pct,
        "avg_duration_sec": sum(regime_durations) / len(regime_durations) if regime_durations else 0,
        "total_transitions": total_transitions,
        "hours_covered": hours_covered,
        "total_seconds": total_seconds,
        "uncertain_pct": regime_pct.get("UNCERTAIN", 0),
        "regime_durations_by_type": regime_durations_by_type,
    }

# ==================== OUTPUT ====================
print("=" * 120)
print("TABLE 1: % TIME IN EACH REGIME (per symbol)")
print("=" * 120)
header = f"{'Regime':<20}" + "".join(f"{s:>14}" for s in SYMBOLS)
print(header)
print("-" * 120)

for r in REGIMES:
    row = f"{r:<20}"
    for sym in SYMBOLS:
        if results[sym]:
            val = results[sym]["regime_pct"].get(r, 0)
            row += f"{val:>13.1f}%"
        else:
            row += f"{'N/A':>14}"
    print(row)

print("-" * 120)

print()
print("=" * 120)
print("TABLE 2: AVG DURATION PER REGIME SESSION (seconds)")
print("=" * 120)
header = f"{'Regime':<20}" + "".join(f"{s:>14}" for s in SYMBOLS)
print(header)
print("-" * 120)

for r in REGIMES:
    row = f"{r:<20}"
    for sym in SYMBOLS:
        if results[sym]:
            durations = results[sym]["regime_durations_by_type"].get(r, [])
            if durations:
                avg = sum(durations) / len(durations)
                row += f"{avg:>13.0f}s"
            else:
                row += f"{'---':>14}"
        else:
            row += f"{'N/A':>14}"
    print(row)

print("-" * 120)

print()
print("=" * 120)
print("TABLE 3: SUMMARY PER SYMBOL")
print("=" * 120)
header = f"{'Metric':<40}" + "".join(f"{s:>14}" for s in SYMBOLS)
print(header)
print("-" * 120)

row = f"{'Hours of data':<40}"
for sym in SYMBOLS:
    if results[sym]:
        row += f"{results[sym]['hours_covered']:>13.1f}h"
    else:
        row += f"{'N/A':>14}"
print(row)

row = f"{'Total transitions':<40}"
for sym in SYMBOLS:
    if results[sym]:
        row += f"{results[sym]['total_transitions']:>14}"
    else:
        row += f"{'N/A':>14}"
print(row)

row = f"{'Transitions per 24h (extrapolated)':<40}"
for sym in SYMBOLS:
    if results[sym] and results[sym]["hours_covered"] > 0:
        per_day = results[sym]["total_transitions"] / results[sym]["hours_covered"] * 24
        row += f"{per_day:>13.1f}"
    else:
        row += f"{'N/A':>14}"
print(row)

row = f"{'Avg regime duration (sec)':<40}"
for sym in SYMBOLS:
    if results[sym]:
        row += f"{results[sym]['avg_duration_sec']:>13.0f}s"
    else:
        row += f"{'N/A':>14}"
print(row)

row = f"{'% time in UNCERTAIN':<40}"
for sym in SYMBOLS:
    if results[sym]:
        row += f"{results[sym]['uncertain_pct']:>13.1f}%"
    else:
        row += f"{'N/A':>14}"
print(row)

print("-" * 120)

# Global UNCERTAIN
total_uncertain_sec = 0
total_all_sec = 0
for sym in SYMBOLS:
    if results[sym]:
        total_all_sec += results[sym]["total_seconds"]
        for r_name, durations in results[sym]["regime_durations_by_type"].items():
            if r_name == "UNCERTAIN":
                total_uncertain_sec += sum(durations)

global_uncertain_pct = (total_uncertain_sec / total_all_sec * 100) if total_all_sec > 0 else 0

print()
print(f"GLOBAL % TIME IN UNCERTAIN: {global_uncertain_pct:.1f}%")
print(f"   (total UNCERTAIN: {total_uncertain_sec/3600:.1f}h out of {total_all_sec/3600:.1f}h total)")
print()

print("Regimes actually observed in logs:")
seen = set()
for t in transitions:
    seen.add(t["new"])
print(f"  {sorted(seen)}")
