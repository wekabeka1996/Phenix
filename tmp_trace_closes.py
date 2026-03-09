import json
from pathlib import Path
from datetime import datetime

# Look up specific order IDs in the core logs to see what triggered their close.
# From order_log_v1, we know these brackets were manually closed:
# 1000000020478364, 1000000020491840, 1000000020495317, 1000000020450174

target_ids = ["1000000020478364", "1000000020491840", "1000000020450174"]
target_symbols = {"ETHUSDT", "BTCUSDT", "XRPUSDT"}

log_dir = Path("logs")

for log_file in sorted(log_dir.glob("aurora_core.log*"), key=lambda x: str(x)):
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if any(t in line for t in target_ids):
                    print(f"[{log_file.name}] {line.strip()}")
                elif "CLOSE" in line and any(s in line for s in target_symbols) and "fsm" in line and "DEC" in line:
                    # Collect DEC:CLOSE to see what prompts it (limit to a few to prevent noise)
                    # We will just print the exact lines where DEC:CLOSE is emitted for these symbols
                    if "result=" in line or "ready to execute" in line:
                        pass # keep it terse for now
    except Exception as e:
        print(f"Error reading {log_file}: {e}")

# Also look for Risk management or Decision making logs explicitly closing or reversing at the time of manual_close
# Timestamps of some manual closes: 1772746560501, 1772745600487, 1772745300436

ts_targets = [1772746560, 1772745600, 1772745300]
print("\n--- Looking for events around manual_close timestamps ---")
for ts in ts_targets:
    dt = datetime.fromtimestamp(ts)
    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    time_str_short = dt.strftime("%H:%M:%S") # Just in case
    print(f"Target Time: {time_str} ({ts})")
    
    for log_file in sorted(log_dir.glob("aurora_core.log*"), key=lambda x: str(x)):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                context = []
                for line in f:
                    context.append(line.strip())
                    if len(context) > 10:
                        context.pop(0)
                        
                    if time_str_short[:5] in line and ("CLOSE" in line or "cancel" in line.lower() or "supersede" in line.lower()):
                        # Found a possible trigger
                        if "adapter" not in line.lower(): # skip standard adapter logs
                            print(f"Found around {time_str_short}: {line.strip()}")
        except Exception:
            pass
