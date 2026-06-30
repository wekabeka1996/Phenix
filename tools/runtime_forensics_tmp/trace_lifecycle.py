import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

rid_events = defaultdict(list)

for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                rid = rec.get("rid")
                if rid:
                    rid_events[rid].append((f.name, idx, ev, rec))
            except Exception as e:
                pass

print(f"Total distinct rids: {len(rid_events)}")
# Let's count combination of events for each rid
combos = defaultdict(int)
for rid, evs in rid_events.items():
    types = tuple(sorted(list(set(e[2] for e in evs))))
    combos[types] += 1

print("\n=== Event combinations per rid ===")
for t, count in sorted(combos.items(), key=lambda x: x[1], reverse=True):
    print(f"- {t}: {count}")

# Print a few samples of interesting rids
print("\n=== Sample rids with ORDER_INTENT but no ORDER_PLACED ===")
sampled = 0
for rid, evs in rid_events.items():
    types = set(e[2] for e in evs)
    if "ORDER_INTENT" in types and "ORDER_PLACED" not in types:
        print(f"rid: {rid} | events: {[e[2] for e in evs]}")
        sampled += 1
        if sampled >= 5:
            break

print("\n=== Sample rids with ORDER_PLACED ===")
sampled = 0
for rid, evs in rid_events.items():
    types = set(e[2] for e in evs)
    if "ORDER_PLACED" in types:
        print(f"rid: {rid} | events: {[e[2] for e in evs]}")
        sampled += 1
        if sampled >= 5:
            break
