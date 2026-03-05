#!/usr/bin/env python3
"""Investigation script: root causes of alpha_search 0 results."""
import json
import datetime
from pathlib import Path

print("=" * 70)
print("ALPHA SEARCH ROOT CAUSE INVESTIGATION")
print("=" * 70)

# 1. data/recorder
rec = Path("data/recorder")
print("\n[1] data/recorder:")
print(f"  exists: {rec.exists()}")
if rec.exists():
    days = sorted(rec.iterdir())
    print(f"  days: {len(days)}")
    if days:
        print(f"  first: {days[0].name}, last: {days[-1].name}")
    csvs = list(rec.rglob("*.csv"))
    print(f"  total CSVs: {len(csvs)}")
    if csvs:
        # Sample per symbol
        syms = set()
        for c in csvs[:20]:
            syms.add(c.stem.split("_")[0] if "_" in c.stem else c.stem)
        print(f"  sample symbols: {sorted(syms)[:5]}")
        print(f"  sample file: {csvs[0].name}")
else:
    print("  MISSING - cannot use build_alpha_input.py")

# 2. alpha_input file
f = Path("logs/alpha_input/alpha_input_v1.jsonl")
print("\n[2] logs/alpha_input/alpha_input_v1.jsonl:")
if f.exists():
    size = f.stat().st_size
    ts = f.stat().st_mtime
    dt = datetime.datetime.fromtimestamp(ts)
    print(f"  size: {size} bytes")
    print(f"  modified: {dt}")
    count = sum(1 for _ in open(f, encoding="utf-8", errors="ignore"))
    print(f"  lines (snapshots): {count}")
    if count > 0:
        with open(f, encoding="utf-8", errors="ignore") as fh:
            first = json.loads(fh.readline())
        print(f"  first record:")
        print(f"    symbol: {first.get('symbol')}")
        print(f"    tf_sec: {first.get('tf_sec')}")
        ts_ms = first.get("ts_ms", 0)
        print(
            f"    ts_ms: {ts_ms} = {datetime.datetime.fromtimestamp(ts_ms/1000)}")
        print(f"    features: {list(first.get('features', {}).keys())[:10]}")
else:
    print("  MISSING")

# 3. features log format
feat = Path("logs/features/BTCUSDT.log")
print("\n[3] logs/features/BTCUSDT.log:")
if feat.exists():
    sz = feat.stat().st_size
    count_f = sum(1 for _ in open(feat, encoding="utf-8", errors="ignore"))
    print(f"  size: {sz//1024} KB, lines: {count_f}")
    with open(feat, encoding="utf-8", errors="ignore") as fh:
        line = fh.readline().strip()
    start = line.find("{")
    if start >= 0:
        d = json.loads(line[start:])
        print(f"  has ts_ms: {'ts_ms' in d}")
        print(f"  has ts: {'ts' in d}")
        print(f"  has symbol: {'symbol' in d}")
        print(f"  has bar_close_ts: {'bar_close_ts' in d}")
        print(f"  has price: {'price' in d}")
        print(f"  has tf_sec: {'tf_sec' in d}")
        print(f"  all keys ({len(d)}): {list(d.keys())}")
else:
    print("  MISSING")

# 4. FMW wiring analysis
print("\n[4] FeatureMirrorWriter event bus wiring:")
log = Path("logs/aurora_core.log")
if log.exists():
    data = log.read_text(encoding="utf-8", errors="ignore")
    lines = data.strip().split("\n")
    fmw_lines = [
        l for l in lines if "FeatureMirrorWriter" in l or "feature_mirror" in l.lower()]
    feat_emit = [l for l in lines if "FEATURES_CALCULATED" in l and (
        "emitted" in l.lower() or "emitting" in l.lower() or "EVT:" in l)]
    print(f"  FMW log lines: {len(fmw_lines)}")
    for l in fmw_lines[:5]:
        print(f"    {l.strip()[:160]}")
    print(f"  FEATURES_CALCULATED emission lines: {len(feat_emit)}")
    for l in feat_emit[:3]:
        print(f"    {l.strip()[:160]}")

    # Time bounds
    first_ts = lines[0][:25] if lines else "?"
    last_ts = lines[-1][:25] if lines else "?"
    print(f"  aurora_core.log timespan: {first_ts} → {last_ts}")
    duration_s = len(lines)  # rough estimate
    print(f"  aurora_core.log lines: {len(lines)}")

# 5. Session analysis
print("\n[5] Session 20260303_114624:")
sess = Path("logs/alpha_search_runtime/20260303_114624")
sess_log = sess / "aggregate" / "alpha_search_domain.log"
if sess_log.exists():
    data = sess_log.read_text(encoding="utf-8", errors="ignore")
    lines = data.strip().split("\n")
    print(f"  Session log lines: {len(lines)}")
    print(f"  First: {lines[0][:120] if lines else '?'}")
    print(f"  Last:  {lines[-1][:120] if lines else '?'}")
    # ingest stats
    ingest_lines = [l for l in lines if "ingest" in l.lower(
    ) or "snapshots_read" in l.lower() or "live_tail" in l.lower()]
    for l in ingest_lines[:5]:
        print(f"  ingest: {l.strip()[:160]}")

print("\n[6] All alpha_search runtime sessions:")
rt_root = Path("logs/alpha_search_runtime")
if rt_root.exists():
    for sess_dir in sorted(rt_root.iterdir()):
        if not sess_dir.is_dir():
            continue
        log_f = sess_dir / "aggregate" / "alpha_search_domain.log"
        ts_str = sess_dir.name
        if log_f.exists():
            # Get final stats from log
            data = log_f.read_text(encoding="utf-8", errors="ignore")
            final_line = ""
            for l in data.split("\n"):
                if "Final stats" in l or "Reactor stopping" in l:
                    final_line = l.strip()
            print(
                f"  {ts_str}: {final_line[:120] if final_line else 'no final stats'}")
        else:
            print(f"  {ts_str}: no log file")
