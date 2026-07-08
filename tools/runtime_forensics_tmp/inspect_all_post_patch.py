import json
from pathlib import Path
from datetime import datetime, timezone

PATCH_TS_MS = 1782845625000

def list_all_post_patch_events():
    path = Path("logs/shadow_critical_event_journal_v1.jsonl")
    if not path.exists():
        return
    
    events_by_name = {}
    total_post_patch = 0
    boot_events = []
    
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            ts = row.get("ts_ms")
            if ts and ts >= PATCH_TS_MS:
                total_post_patch += 1
                name = row.get("event_name")
                events_by_name[name] = events_by_name.get(name, 0) + 1
                
                # Check for boot/restore events
                if "BOOT" in name or "RESTORE" in name or "START" in name or "INIT" in name or "RESET" in name:
                    dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat()
                    boot_events.append((dt, ts, name, row.get("verb")))
                    
    print(f"Total post-patch events: {total_post_patch}")
    print("\n--- Event Distribution ---")
    for name, count in sorted(events_by_name.items(), key=lambda x: x[1], reverse=True):
        print(f"  {name}: {count}")
        
    print("\n--- Boot/Restore/Reset Events after Patch ---")
    if boot_events:
        for dt, ts, name, verb in boot_events:
            print(f"  [{dt}] ts={ts} event={name} verb={verb}")
    else:
        print("  No boot/restore/reset events found.")

if __name__ == "__main__":
    list_all_post_patch_events()
