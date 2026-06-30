import json
from pathlib import Path
from collections import Counter

ROOT = Path(r"C:\Users\wekab\Music\Phenix")

def check_wal_verbs(p):
    if not p.exists():
        return
    print(f"\n=== Verbs in {p.relative_to(ROOT).as_posix()} ===")
    verbs = Counter()
    with open(p, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                verbs[rec.get("verb")] += 1
            except:
                pass
    print(dict(verbs.most_common(20)))

check_wal_verbs(ROOT / "ops" / "wal" / "2026-06-17.jsonl")
check_wal_verbs(ROOT / "ops" / "wal" / "2026-06-18.jsonl")
check_wal_verbs(ROOT / "ops" / "wal" / "old" / "order_log_v1.jsonl")
