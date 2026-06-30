import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

print("=== Checking event types and structures in order_log_old ===")
sample_events = {}
for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type") or "UNKNOWN"
                if ev not in sample_events:
                    sample_events[ev] = (f.name, idx, rec)
            except Exception as e:
                pass

for ev, (fname, idx, rec) in sample_events.items():
    print(f"\nEvent Type: {ev} (Found in {fname} line {idx})")
    print("Keys:", list(rec.keys()))
    # Let's print some interesting fields
    for k in ("decision", "intent", "order", "fill", "signal", "safety_gates", "safety_gate_snapshot", "low_vol_cost_floor", "price_motion_context", "context", "payload", "reason", "reject_reason", "nrr_code", "gate"):
        if k in rec:
            print(f"  Field '{k}' type: {type(rec[k])}")
            print(f"  Field '{k}' sample: {json.dumps(rec[k], indent=2)[:500]}...")
        # Check if there are nested keys containing these keywords
        for nk, nv in rec.items():
            if isinstance(nv, dict):
                for nkk in nv.keys():
                    if k in nkk:
                        print(f"  Nested field '{nk}.{nkk}' type: {type(nv[nkk])}")
                        print(f"  Nested field '{nk}.{nkk}' sample: {json.dumps(nv[nkk], indent=2)[:500]}...")
