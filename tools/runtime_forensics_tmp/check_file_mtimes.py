import os
from pathlib import Path
from datetime import datetime, timezone

def print_mtime(path_str):
    path = Path(path_str)
    if not path.exists():
        print(f"{path_str} does not exist")
        return
    mtime = path.stat().st_mtime
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    print(f"File: {path.name:<40} | MTime: {mtime} -> {dt.isoformat()}")

print_mtime("config/aurora/domains.yaml")
print_mtime("apps/reference/config/domains/decision_making.py")
print_mtime("apps/reference/domains/decision_making/gates/safety_gates.py")
print_mtime("tests/config/_artifacts/decision_making_contract.generated.json")
print_mtime("logs/shadow_critical_event_journal_v1.jsonl")
