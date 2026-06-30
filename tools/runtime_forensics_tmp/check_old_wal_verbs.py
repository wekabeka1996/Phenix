import json
from pathlib import Path
from collections import Counter

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
p = ROOT / "ops" / "wal" / "old" / "2026-06-14.jsonl"

print("=== Verbs in ops/wal/old/2026-06-14.jsonl ===")
verbs = Counter()
with open(p, 'r', encoding='utf-8', errors='replace') as fh:
    for idx, line in enumerate(fh, 1):
        try:
            rec = json.loads(line)
            verbs[rec.get("verb")] += 1
        except:
            pass
print(dict(verbs.most_common(20)))
