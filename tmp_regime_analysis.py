#!/usr/bin/env python3
"""Analyse regime‐detector logs for the last 7 days."""

import json, re, os
from datetime import datetime, timedelta
from collections import defaultdict

LOGFILE = os.path.join("logs", "domain_regime_detector.log")
BARS_FILE = os.path.join("logs", "mean_reversion", "bars_300s.jsonl")
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
ALL_REGIMES = [
    "TREND_UP", "TREND_DOWN", "FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH",
    "MEAN_REVERSION", "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNCERTAIN",
]
BAR_DURATION = 300  # seconds

cutoff = datetime.now() - timedelta(days=7)
now = datetime.now()

# ── 1. Parse transitions from domain_regime_detector.log ──
transition_re = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .* "
    r"\[(\w+)\] Regime updated: (\w+)\s*[->]+\s*(\w+)"
)

transitions = defaultdict(list)
with open(LOGFILE, "r", encoding="utf-8") as f:
    for line in f:
        m = transition_re.search(line)
        if not m:
            continue
        ts_str, symbol, old_reg, new_reg = m.groups()
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        if ts >= cutoff and symbol in SYMBOLS:
            transitions[symbol].append((ts, old_reg, new_reg))

# ── 2. Parse bars_300s.jsonl ──
bar_regimes = defaultdict(list)  # symbol -> [(ts, regime)]
with open(BARS_FILE, "r", encoding="utf-8") as f:
    for line in f:
        try:
            rec = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        sym = rec.get("symbol", "")
        if sym not in SYMBOLS:
            continue
        ts_human = rec.get("ts_human", "")
        regime = rec.get("signal", {}).get("regime", "UNKNOWN")
        try:
            ts = datetime.strptime(ts_human, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if ts >= cutoff:
            bar_regimes[sym].append((ts, regime))

# ── 3. Output ──
print("=" * 94)
print("   REGIME ANALYSIS  |  Last 7 days  |  2026-02-16 .. 2026-02-23")
print("=" * 94)

total_uncertain_time = 0
total_time = 0

for sym in SYMBOLS:
    bars = bar_regimes.get(sym, [])
    trans = transitions.get(sym, [])

    regime_cnt = defaultdict(int)
    for _, regime in bars:
        regime_cnt[regime] += 1

    total_bars = sum(regime_cnt.values())
    total_sec  = total_bars * BAR_DURATION

    # transitions / day
    if trans:
        span_days = max((trans[-1][0] - trans[0][0]).total_seconds() / 86400, 1)
        tpd = len(trans) / span_days
    else:
        tpd = 0.0

    # average regime duration
    if len(trans) >= 2:
        durs = [(trans[i+1][0] - trans[i][0]).total_seconds() for i in range(len(trans) - 1)]
        avg_dur = sum(durs) / len(durs)
    elif total_bars > 0 and trans:
        avg_dur = total_sec / max(len(trans), 1)
    else:
        avg_dur = total_sec

    unc_pct = (regime_cnt.get("UNCERTAIN", 0) / total_bars * 100) if total_bars else 0

    total_uncertain_time += regime_cnt.get("UNCERTAIN", 0) * BAR_DURATION
    total_time += total_sec

    print()
    print(f"+{'='*92}+")
    print(f"|  {sym:<89} |")
    print(f"+{'-'*42}+{'-'*15}+{'-'*16}+{'-'*16}+")
    print(f"| {'Regime':<41}| {'% time':>13} | {'Bars (5m)':>14} | {'Hours':>14} |")
    print(f"+{'-'*42}+{'-'*15}+{'-'*16}+{'-'*16}+")

    for regime in ALL_REGIMES:
        c = regime_cnt.get(regime, 0)
        pct = (c / total_bars * 100) if total_bars else 0
        hrs = c * BAR_DURATION / 3600
        flag = "  <--" if regime == "UNCERTAIN" and pct > 30 else ""
        print(f"| {regime:<41}| {pct:>12.1f}% | {c:>14} | {hrs:>13.1f}h |{flag}")

    print(f"+{'-'*42}+{'-'*15}+{'-'*16}+{'-'*16}+")
    print(f"| {'TOTAL':<41}| {'100.0%':>13} | {total_bars:>14} | {total_sec/3600:>13.1f}h |")
    print(f"+{'-'*42}+{'-'*15}+{'-'*16}+{'-'*16}+")
    print(f"|  Avg regime duration : {avg_dur:>8.0f} sec  ({avg_dur/60:>6.1f} min)                             |")
    print(f"|  Transitions / day   : {tpd:>8.1f}                                                    |")
    print(f"|  % time UNCERTAIN    : {unc_pct:>8.1f}%                                                   |")
    print(f"|  Total transitions   : {len(trans):>8}                                                    |")
    print(f"+{'='*92}+")

# ── 4. Global UNCERTAIN ──
g_unc = (total_uncertain_time / total_time * 100) if total_time else 0
print()
print("=" * 94)
print(f"   GLOBAL UNCERTAIN : {g_unc:.1f}%    ({total_uncertain_time/3600:.1f}h / {total_time/3600:.1f}h)")
print("=" * 94)

# ── 5. Compact summary ──
print()
print("+-------------+----------+----------+----------+----------+----------+---------+--------+---------+")
print(f"| {'Symbol':>11} | {'MEAN_REV':>8} | {'HIGH_VOL':>8} | {'LOW_VOL':>8} | {'UNCERTAN':>8} | {'Avg dur':>8} | {'Trn/day':>7} | {'Bars':>6} | {'Hours':>7} |")
print("+-------------+----------+----------+----------+----------+----------+---------+--------+---------+")

for sym in SYMBOLS:
    bars = bar_regimes.get(sym, [])
    trans = transitions.get(sym, [])
    rc = defaultdict(int)
    for _, r in bars:
        rc[r] += 1
    tb = sum(rc.values())
    if not tb:
        continue
    mr = rc.get("MEAN_REVERSION", 0) / tb * 100
    hv = rc.get("HIGH_VOLATILITY", 0) / tb * 100
    lv = rc.get("LOW_VOLATILITY", 0) / tb * 100
    un = rc.get("UNCERTAIN", 0) / tb * 100
    if trans and len(trans) >= 2:
        ds = max((trans[-1][0] - trans[0][0]).total_seconds() / 86400, 1)
        tpd2 = len(trans) / ds
        durs2 = [(trans[i+1][0] - trans[i][0]).total_seconds() for i in range(len(trans)-1)]
        ad = sum(durs2) / len(durs2)
    else:
        tpd2 = 0
        ad = tb * BAR_DURATION
    hrs = tb * BAR_DURATION / 3600
    print(f"| {sym:>11} | {mr:>7.1f}% | {hv:>7.1f}% | {lv:>7.1f}% | {un:>7.1f}% | {ad/60:>6.0f}m  | {tpd2:>7.1f} | {tb:>6} | {hrs:>6.1f}h |")

print("+-------------+----------+----------+----------+----------+----------+---------+--------+---------+")
print(f"| {'SYSTEM':>11} |          |          |          | {g_unc:>7.1f}% |          |         |        | {total_time/3600:>6.1f}h |")
print("+-------------+----------+----------+----------+----------+----------+---------+--------+---------+")

# ── 6. Recent 24h transitions ──
print()
print("-- RECENT TRANSITIONS (last 24h) --")
recent_cutoff = datetime.now() - timedelta(hours=24)
for sym in SYMBOLS:
    recent = [(ts, o, n) for ts, o, n in transitions.get(sym, []) if ts >= recent_cutoff]
    if recent:
        print(f"\n  {sym}:")
        for ts, o, n in recent[-10:]:
            print(f"    {ts.strftime('%m-%d %H:%M')}  {o:>16} -> {n}")
    else:
        print(f"\n  {sym}: no transitions in last 24h")
