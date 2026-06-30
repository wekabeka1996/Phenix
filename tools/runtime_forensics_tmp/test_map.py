import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

# Load all intents
intents = []
for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev == "ORDER_INTENT":
                    intents.append((f.name, idx, rec))
            except:
                pass

# Associate reserve to decision
uuid_to_dec = {}
dec_to_uuid = {}

for i in range(len(intents)):
    fname, idx, rec = intents[i]
    rid = rec.get("rid", "")
    if rid.startswith("reserve_"):
        uuid_val = rid.split("reserve_", 1)[1]
        # Look forward for the first non-reserve intent with the same symbol and side
        for j in range(i+1, min(i+10, len(intents))):
            jf, jidx, jrec = intents[j]
            jrid = jrec.get("rid", "")
            if not jrid.startswith("reserve_") and jrec.get("symbol") == rec.get("symbol") and jrec.get("side") == rec.get("side"):
                time_diff = jrec.get("timestamp", 0) - rec.get("timestamp", 0)
                if abs(time_diff) < 5000:
                    uuid_to_dec[uuid_val] = jrid
                    dec_to_uuid[jrid] = uuid_val
                    break

print(f"Total reserve UUIDs mapped to decision RIDs: {len(uuid_to_dec)}")
print("Sample mappings:")
for k, v in list(uuid_to_dec.items())[:10]:
    print(f"- UUID: {k} <-> Dec RID: {v}")
