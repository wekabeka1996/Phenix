import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"
SHADOW_JOURNAL = ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl"

print("--- EXEC STATS FOR idem-fill-1 ---")
with open(EXEC_STATS, "r", encoding="utf-8") as f:
    for line in f:
        if "idem-fill-1" in line:
            obj = json.loads(line)
            ts = obj.get("recorded_ts_ms") or 0
            if ts > T8_TS_MS:
                print(f"ts={ts} symbol={obj.get('symbol')} side={obj.get('side')} entry_ts={obj.get('entry_ts_ms')} entry_price={obj.get('entry_price')} qty={obj.get('qty')} prov_status={obj.get('provisional_status')}")
                break

print("\n--- SHADOW JOURNAL FOR idem-fill-1 ---")
count = 0
with open(SHADOW_JOURNAL, "r", encoding="utf-8") as f:
    for line in f:
        if "idem-fill-1" in line:
            obj = json.loads(line)
            print(f"ts={obj.get('ts_ms')} event={obj.get('event_name')} strategy={obj.get('strategy_id')} symbol={obj.get('symbol')}")
            count += 1
            if count >= 5:
                break
