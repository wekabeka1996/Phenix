import json
from pathlib import Path
from collections import Counter

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

print("=== Scanning ORDER_INTENT for low_vol_cost_floor ===")
total_intents = 0
with_low_vol = 0
strategies = Counter()
symbols = Counter()

for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev == "ORDER_INTENT":
                    total_intents += 1
                    meta = rec.get("metadata") or {}
                    low_vol = meta.get("low_vol_cost_floor")
                    strat = meta.get("strategy_id") or "unknown"
                    sym = rec.get("symbol")
                    if low_vol:
                        with_low_vol += 1
                        strategies[strat] += 1
                        symbols[sym] += 1
            except Exception as e:
                pass

print(f"Total ORDER_INTENTs: {total_intents}")
print(f"With low_vol_cost_floor metadata: {with_low_vol}")
print("Strategies with low_vol_cost_floor:", dict(strategies))
print("Symbols with low_vol_cost_floor:", dict(symbols))
