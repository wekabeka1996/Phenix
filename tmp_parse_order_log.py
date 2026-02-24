import collections, json
from pathlib import Path

path = Path('logs/order_log_v1.jsonl')
text = path.read_text(encoding='utf-8', errors='replace')

dec = json.JSONDecoder()
i = 0
n = 0
counts = collections.Counter()
keys = collections.Counter()

while i < len(text):
    ch = text[i]
    if ch.isspace():
        i += 1
        continue
    if ch != '{':
        nxt = text.find('{', i)
        if nxt == -1:
            break
        i = nxt
        continue
    try:
        obj, j = dec.raw_decode(text, i)
    except Exception:
        nxt = text.find('{', i+1)
        if nxt == -1:
            break
        i = nxt
        continue
    i = j
    n += 1
    et = obj.get('event_type') or obj.get('type') or obj.get('event')
    if et:
        counts[str(et)] += 1
    for k in obj.keys():
        keys[k] += 1

print('objects_parsed', n)
print('top_event_types')
for k, v in counts.most_common(40):
    print(f'{k}\t{v}')
print('top_keys')
for k, v in keys.most_common(25):
    print(f'{k}\t{v}')
