import os
from pathlib import Path
from datetime import datetime, timezone

LOGS_DIR = Path("logs")
PATCH_TIME = datetime.fromisoformat("2026-06-30T18:47:37+00:00")

def check_startup():
    print(f"Scanning logs for startup events after {PATCH_TIME.isoformat()}...")
    for file_path in LOGS_DIR.glob("*.log*"):
        if not file_path.name.startswith(("aurora_core", "domain_decision_making")):
            continue
        print(f"Checking {file_path.name}...")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Logs usually start with a timestamp like "2026-06-30 21:56:54,600"
                parts = line.split(" - ")
                if len(parts) < 2:
                    continue
                ts_str = parts[0].strip()
                try:
                    # try to parse "2026-06-30 21:56:54,600"
                    # which is Kiev local time (UTC+3)
                    dt_local = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
                    dt_utc = dt_local.replace(tzinfo=timezone.utc) # Wait, it is UTC+3!
                    # Let's adjust for UTC+3: subtract 3 hours
                    # Or we can just convert to epoch timestamp:
                    epoch = dt_local.timestamp() - 3*3600
                    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
                except ValueError:
                    continue
                
                if dt >= PATCH_TIME:
                    # Check if the line indicates startup/init
                    l_lower = line.lower()
                    if "start" in l_lower or "boot" in l_lower or "init" in l_lower or "load" in l_lower or "facade" in l_lower or "connect" in l_lower:
                        print(f"  [{dt.isoformat()}] {line.strip()[:150]}")

if __name__ == "__main__":
    check_startup()
