import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")

# Let's find some TRADE_INTENT_PROPOSED events in all WAL files
wal_files = sorted(list((ROOT / "ops" / "wal").glob("*.jsonl"))) + sorted(list((ROOT / "ops" / "wal" / "old").glob("*.jsonl")))

count = 0
for f in wal_files:
    if f.name == "order_log_v1.jsonl":
        continue
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                if rec.get("verb") == "TRADE_INTENT_PROPOSED":
                    print(f"\nFile: {f.relative_to(ROOT).as_posix()} | Line: {idx} | rid: {rec.get('rid')}")
                    # Let's inspect the payload
                    pld = rec.get("pld") or {}
                    print("Keys in pld:", list(pld.keys()))
                    for k in ("order", "features", "safety_gates", "safety_gate_snapshot", "metadata", "decision_context", "context"):
                        if k in pld:
                            print(f"  pld[{k}]: type={type(pld[k])}")
                            print(json.dumps(pld[k], indent=2)[:1000])
                    count += 1
                    if count >= 3:
                        break
            except Exception as e:
                pass
    if count >= 3:
        break
