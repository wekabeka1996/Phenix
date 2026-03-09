import json
from pathlib import Path
from collections import Counter

path = Path('logs/order_log_v1.jsonl')
lines = path.read_text(encoding='utf-8', errors='replace').strip().split('\n')

orders = {}
cancels = []

for line in lines:
    if not line.strip(): continue
    try:
        obj = json.loads(line)
        et = obj.get('event_type')
        oid = obj.get('order_id') or obj.get('reservation_id')
        if not oid: continue
        
        if oid not in orders:
            orders[oid] = []
        orders[oid].append(obj)
        
        if et == 'ORDER_CANCELLED':
            cancels.append(obj)
            
    except Exception as e:
        pass

reasons = Counter()
for c in cancels:
    reasons[(c.get('why', ''), c.get('reason', ''))] += 1

print("Cancel reasons breakdown:")
for k, v in reasons.items():
    print(f"  {k}: {v}")

print("\nDetailed fast cancellations (lifetime < 5 mins):")
for c in cancels:
    oid = c.get('order_id') or c.get('reservation_id')
    ts = c.get('timestamp', 0)
    if oid in orders:
        placed = [o for o in orders[oid] if o.get('event_type') == 'ORDER_PLACED']
        if placed:
            pts = placed[0].get('timestamp', 0)
            diff_sec = (ts - pts) / 1000.0
            if diff_sec > 0 and diff_sec < 300: # 5 mins
                print(f"[{ts}] {oid} alive for {diff_sec}s - why: {c.get('why')}, reason: {c.get('reason')}")
