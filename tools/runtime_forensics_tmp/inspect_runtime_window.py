import json
import os
from pathlib import Path

LOGS_DIR = Path("logs")

def get_file_bounds(filename):
    path = LOGS_DIR / filename
    if not path.exists():
        print(f"{filename} does not exist")
        return None
    
    first_line = None
    last_line = None
    file_size = path.stat().st_size
    
    with open(path, "rb") as f:
        # Read first line
        first_line = f.readline().decode('utf-8', errors='ignore').strip()
        
        # Read last line
        if file_size > 0:
            # seek to near end
            seek_pos = max(0, file_size - 10000)
            f.seek(seek_pos)
            lines = f.readlines()
            if lines:
                last_line = lines[-1].decode('utf-8', errors='ignore').strip()
                
    print(f"File: {filename} (Size: {file_size} bytes)")
    print(f"  First: {first_line[:200]}")
    print(f"  Last : {last_line[:200] if last_line else 'None'}")
    return first_line, last_line

if __name__ == "__main__":
    get_file_bounds("order_log_v1.jsonl")
    get_file_bounds("shadow_critical_event_journal_v1.jsonl")
    get_file_bounds("trade_lifecycle.jsonl")
    get_file_bounds("regime_confidence_audit_v1.jsonl")
