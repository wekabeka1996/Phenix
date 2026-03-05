#!/usr/bin/env python3
"""Analyze feature_engineering log to understand format."""
import json
from pathlib import Path

LOG = Path("logs/domain_feature_engineering.log")
events = {}
sample_feat = None

with open(LOG, encoding="utf-8", errors="ignore") as f:
    for line in f:
        start = line.find("{")
        if start < 0:
            continue
        try:
            d = json.loads(line[start:])
            ev = d.get("event", "?")
            events[ev] = events.get(ev, 0) + 1
            if ev == "FEATURES_CALCULATED" and sample_feat is None:
                sample_feat = d
        except Exception:
            pass

print("Feature events:")
for k, v in sorted(events.items(), key=lambda x: -x[1])[:15]:
    print(f"  {k}: {v}")

if sample_feat:
    print("\nSample FEATURES_CALCULATED:")
    feats = sample_feat.get("features", {})
    print(f"  symbol: {sample_feat.get('symbol')}")
    print(f"  price: {sample_feat.get('price')}")
    print(f"  tf_sec: {sample_feat.get('tf_sec')}")
    print(f"  bar_close_ts: {sample_feat.get('bar_close_ts')}")
    print(f"  ts_ms: {sample_feat.get('ts_ms')}")
    print(f"  regime: {sample_feat.get('regime')}")
    print(f"  feature keys ({len(feats)}): {list(feats.keys())[:15]}")

    # Check for alpha_input required keys
    required = ["obi", "delta_price", "macro_resid",
                "rsi_14", "bb_position", "macd_signal"]
    print("\n  Alpha-relevant features present:")
    for k in required:
        v = feats.get(k)
        print(f"    {k}: {v}")
else:
    print("\nNo FEATURES_CALCULATED events found.")
