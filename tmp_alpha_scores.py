#!/usr/bin/env python3
"""Analyze domain_alpha_search.log for score events and PnL."""
import json
from pathlib import Path

LOG = Path("logs/domain_alpha_search.log")

events = {}
score_data = []

with open(LOG, encoding="utf-8", errors="ignore") as f:
    for line in f:
        start = line.find("{")
        if start < 0:
            continue
        try:
            d = json.loads(line[start:])
            ev = d.get("event", "?")
            events[ev] = events.get(ev, 0) + 1
            if ev == "SCORE_EMITTED":
                score_data.append(d)
        except Exception:
            pass

print("=== Event distribution ===")
for k, v in sorted(events.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

print(f"\n=== Score samples (first 10) ===")
for s in score_data[:10]:
    sym = s.get("symbol", "?")
    score = s.get("score", 0)
    conf = s.get("confidence", 0)
    thresh = s.get("threshold", 0)
    provider = s.get("provider_id", "?")
    model = s.get("model_name", "?")
    side = "BUY" if score > thresh else (
        "SELL" if score < -thresh else "NEUTRAL")
    print(f"  {sym:<10} score={score:+.4f} conf={conf:.3f} thresh={thresh} | {provider}/{model} -> {side}")

# Stats by symbol
print("\n=== Per-symbol scoring ===")
by_sym = {}
for s in score_data:
    sym = s.get("symbol", "?")
    sc = s.get("score", 0)
    if sym not in by_sym:
        by_sym[sym] = {"count": 0, "buy": 0,
                       "sell": 0, "neutral": 0, "scores": []}
    by_sym[sym]["count"] += 1
    by_sym[sym]["scores"].append(sc)
    thresh = s.get("threshold", 0.15)
    if sc > thresh:
        by_sym[sym]["buy"] += 1
    elif sc < -thresh:
        by_sym[sym]["sell"] += 1
    else:
        by_sym[sym]["neutral"] += 1

for sym, data in sorted(by_sym.items()):
    avg = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
    print(
        f"  {sym}: total={data['count']} BUY={data['buy']} SELL={data['sell']} NEUTRAL={data['neutral']} avg_score={avg:+.4f}")
