import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")

def check_file_for_keys(p, keys):
    if not p.exists():
        return
    print(f"Checking {p.relative_to(ROOT).as_posix()}...")
    with open(p, 'r', encoding='utf-8', errors='replace') as fh:
        count = 0
        for line in fh:
            if any(k in line for k in keys):
                try:
                    rec = json.loads(line)
                    print(f"Found line matching key: keys in record: {list(rec.keys())}")
                    # Print record sample
                    print(json.dumps(rec, indent=2)[:500])
                    count += 1
                    if count >= 3:
                        break
                except:
                    pass

check_file_for_keys(ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl", ["pm_norm_60s", "trend_dir", "safety_gates"])
check_file_for_keys(ROOT / "logs" / "trade_lifecycle.jsonl", ["pm_norm_60s", "trend_dir", "safety_gates"])
check_file_for_keys(ROOT / "ops" / "wal" / "2026-06-17.jsonl", ["pm_norm_60s", "trend_dir", "safety_gates"])
