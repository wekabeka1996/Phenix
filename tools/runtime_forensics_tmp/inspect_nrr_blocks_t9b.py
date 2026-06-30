import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
LOG_FILES = [
    ROOT / "logs" / "order_log_v1.20260619T000003Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.20260620T000005Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.jsonl",
]

count = 0
for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
                if ts < T8_TS_MS:
                    continue
                if obj.get("event_type") == "DECISION_INTENT_REJECTED":
                    nrr = obj.get("nrr_code")
                    if nrr in ("NRR-027", "NRR-028", "NRR-029", "NRR-030"):
                        print(f"\n--- RECORD {count} ---")
                        print(json.dumps(obj, indent=2))
                        count += 1
                        if count >= 3:
                            break
            except Exception as e:
                pass
    if count >= 3:
        break
