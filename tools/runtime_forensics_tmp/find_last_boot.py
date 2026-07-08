import json
from pathlib import Path
from datetime import datetime, timezone

def find_latest_boot_events():
    path = Path("logs/shadow_critical_event_journal_v1.jsonl")
    if not path.exists():
        print("shadow journal does not exist")
        return
    
    boot_events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            name = row.get("event_name", "")
            ts = row.get("ts_ms")
            if "BOOT" in name or "RESTORE" in name or "RESET" in name:
                dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat()
                boot_events.append((dt, ts, name, row))
                
    print(f"Total boot/restore events: {len(boot_events)}")
    print("\n--- Last 5 boot/restore/reset events in the journal ---")
    for dt, ts, name, row in boot_events[-5:]:
        print(f"  [{dt}] ts={ts} event={name}")
        # print first few payload keys
        if "payload" in row:
            p = row["payload"]
            print(f"    Payload keys: {list(p.keys()) if isinstance(p, dict) else type(p)}")
            if isinstance(p, dict) and "config" in p:
                print(f"    Config present: {type(p['config'])}")

if __name__ == "__main__":
    find_latest_boot_events()
