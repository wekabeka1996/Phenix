import json
from pathlib import Path
from datetime import datetime, timezone

PATCH_TS_MS = 1782845625000  # 2026-06-30T18:53:45Z

def scan_shadow_journal():
    path = Path("logs/shadow_critical_event_journal_v1.jsonl")
    if not path.exists():
        print("shadow journal does not exist")
        return
    
    print(f"Scanning {path.name} for events after patch...")
    post_patch_count = 0
    line_num = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line_num += 1
            if not line.strip():
                continue
            try:
                evt = json.loads(line)
            except Exception as e:
                print(f"Error parsing line {line_num}: {line[:100]}... Error: {e}")
                continue
            ts = evt.get("ts_ms")
            if ts and ts >= PATCH_TS_MS:
                post_patch_count += 1
                dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat()
                event_name = evt.get("event_name")
                verb = evt.get("verb")
                op = evt.get("op")
                print(f"[{dt}] ts={ts} event={event_name} verb={verb} op={op}")
                if event_name in ("RESTORE:EXECUTION_TRUTH_HARDENING_RESET", "EVT:BOOTSTRAP_COMPLETED", "EVT:SYSTEM_BOOT"):
                     print(f"  Full event: {json.dumps(evt)}")
    print(f"Total post-patch events in shadow journal: {post_patch_count}")

if __name__ == "__main__":
    scan_shadow_journal()
