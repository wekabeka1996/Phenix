import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

# Let's inspect some DECISION_INTENT_REJECTED and ORDER_INTENT events to search for trend and price motion keys
for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev in ("DECISION_INTENT_REJECTED", "ORDER_INTENT"):
                    # Let's recursively search for keys like "trend", "pm_norm", "price_motion", "consecutive", "veto"
                    found = []
                    def search_dict(d, path=""):
                        if isinstance(d, dict):
                            for k, v in d.items():
                                if any(x in k.lower() for x in ("trend", "pm_norm", "price_motion", "consecutive", "veto")):
                                    found.append(f"{path}.{k} = {v}")
                                search_dict(v, f"{path}.{k}")
                        elif isinstance(d, list):
                            for i, v in enumerate(d):
                                search_dict(v, f"{path}[{i}]")
                    search_dict(rec)
                    if found:
                        print(f"\nFile {f.name} Line {idx} | Event: {ev} | rid: {rec.get('rid')}")
                        for item in found[:10]:
                            print(f"  {item}")
            except Exception as e:
                pass
