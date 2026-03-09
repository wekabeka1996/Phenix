import json
from pathlib import Path

log_file = Path("logs/order_log_v1.jsonl")

md_amr_intents = 0
md_amr_placed = 0
md_amr_filled = 0

try:
    with open(log_file, "r") as f:
        for line in f:
            try:
                data = json.loads(line)
                
                # Some logs put strategy_id in root, some in payload, some in context
                strategy = None
                
                if "strategy_id" in data:
                    strategy = data["strategy_id"]
                elif "payload" in data and isinstance(data["payload"], dict) and "strategy_id" in data["payload"]:
                    strategy = data["payload"]["strategy_id"]
                elif "context" in data and isinstance(data["context"], dict) and "strategy_id" in data["context"]:
                    strategy = data["context"]["strategy_id"]
                elif "meta" in data and isinstance(data["meta"], dict) and "strategy_id" in data["meta"]:
                    strategy = data["meta"]["strategy_id"]
                    
                # In case it's nested differently for intents vs placed
                pld = data.get("payload", {})
                if isinstance(pld, dict) and pld.get("strategy_id") == "md_amr":
                    strategy = "md_amr"
                    
                if strategy == "md_amr" or (isinstance(pld, dict) and "md_amr" in str(pld)):
                    event_type = data.get("event")
                    if event_type == "ORDER_INTENT":
                        md_amr_intents += 1
                    elif event_type == "ORDER_PLACED":
                        md_amr_placed += 1
                    elif event_type == "ORDER_FILLED":
                        md_amr_filled += 1
            except json.JSONDecodeError:
                pass
except FileNotFoundError:
    print("Log file not found.")

print(f"MD_AMR Intents: {md_amr_intents}")
print(f"MD_AMR Placed Orders: {md_amr_placed}")
print(f"MD_AMR Filled Orders: {md_amr_filled}")

# Let's also grep aurora_core for md_amr trades specifically if jsonl is empty
import os
import glob

# just in case
print("--- Grep logs for md_amr intent/placed ---")
count = 0
for f in glob.glob("logs/aurora_core.log*"):
    with open(f, "r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            if "TRADE_INTENT" in line and "md_amr" in line:
                count += 1
                if count <= 5:
                    print(f"[{f}] {line.strip()}")
print(f"Total TRADE_INTENT from md_amr in core logs: {count}")

