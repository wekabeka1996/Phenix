import json
from pathlib import Path
from collections import Counter

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

blocked_reasons = Counter()

for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev == "STRATEGY_DECISION_BLOCKED":
                    rc = rec.get("reason_code") or "NONE"
                    reason = rec.get("reason") or "NONE"
                    blocked_reasons[(rc, reason)] += 1
            except Exception as e:
                pass

print("=== STRATEGY_DECISION_BLOCKED Reasons ===")
for (rc, r), count in blocked_reasons.most_common(50):
    print(f"- Code: {rc} | Reason: {r} | Count: {count}")
