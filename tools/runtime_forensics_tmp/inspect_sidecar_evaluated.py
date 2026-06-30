import json
from pathlib import Path

ROOT = Path(".")
TRADE_LIFECYCLE = ROOT / "logs" / "trade_lifecycle.jsonl"

print("--- SIDECAR EVALUATED SAMPLE ---")
with open(TRADE_LIFECYCLE, "r", encoding="utf-8") as f:
    for line in f:
        if "POSITION_POLICY_SIDECAR_EVALUATED" in line:
            obj = json.loads(line)
            # Print a clean dump of the keys and the position_snapshot
            print("Keys:", list(obj.keys()))
            if "position_snapshot" in obj:
                print("position_snapshot keys:", list(obj["position_snapshot"].keys()))
                print("position_snapshot:", json.dumps(obj["position_snapshot"], indent=2))
            break
