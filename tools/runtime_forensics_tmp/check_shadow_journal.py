import json
from pathlib import Path
from collections import Counter

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
p = ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl"

print("=== Event/Verb distribution in shadow_critical_event_journal_v1.jsonl ===")
verbs = Counter()
ops = Counter()
if p.exists():
    with open(p, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                verbs[rec.get("verb")] += 1
                ops[rec.get("op")] += 1
            except:
                pass
    print("Verbs:", dict(verbs))
    print("Ops:", dict(ops))
else:
    print("File does not exist")
