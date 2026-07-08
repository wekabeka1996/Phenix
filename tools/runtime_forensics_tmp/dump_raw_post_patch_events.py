import json
from pathlib import Path

PATCH_TS_MS = 1782845625000

def dump_raw_post_patch_events():
    path = Path("logs/shadow_critical_event_journal_v1.jsonl")
    if not path.exists():
        return
    print("\n--- Raw Shadow Journal post-patch rows ---")
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
                event_name = row.get("event_name")
                if event_name in ("EVT:TRADE_INTENT_REJECTED", "EVT:GATE_CHAIN_TRACE", "EVT:ORDER_FILLED", "EVT:ORDER_PLACED"):
                    print(f"Row: {json.dumps(row, indent=2)}")

dump_raw_post_patch_events()
