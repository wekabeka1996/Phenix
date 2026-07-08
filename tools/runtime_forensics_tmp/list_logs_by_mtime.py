from pathlib import Path
from datetime import datetime, timezone

LOGS_DIR = Path("logs")
files = list(LOGS_DIR.glob("*"))
files.sort(key=lambda x: x.stat().st_mtime)

print("=== Log files by mtime ===")
for f in files:
    mtime = f.stat().st_mtime
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    print(f"  File: {f.name:<60} | MTime: {dt.isoformat()}")
