import json
from collections import defaultdict

lifecycle_rids = []
lifecycle_records = {}

with open('logs/trade_lifecycle.jsonl', 'r') as f:
    for line in f:
        try:
            rec = json.loads(line)
            if rec.get('status') == 'ORPHANED_TTL':
                rid = rec['rid']
                lifecycle_rids.append(rid)
                lifecycle_records[rid] = rec
        except Exception:
            pass

print(f"Found {len(lifecycle_rids)} ORPHANED_TTL rids")

events_by_rid = defaultdict(list)
files_to_check = [
    'logs/order_log_v1.jsonl',
    'logs/shadow_critical_event_journal_v1.jsonl',
    'logs/aurora_events.jsonl'
]

for file_path in files_to_check:
    try:
        with open(file_path, 'r') as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    rid = rec.get('rid')
                    if rid in lifecycle_records:
                        # try to get some timestamp
                        ts = rec.get('timestamp') or rec.get('ts_ms') or rec.get('order_ts_ms') or 0
                        event_type = rec.get('event') or rec.get('type') or rec.get('status') or rec.get('message_type') or str(rec)
                        events_by_rid[rid].append((ts, file_path, event_type, rec))
                except Exception:
                    pass
    except FileNotFoundError:
        pass

for rid in lifecycle_rids:
    print(f"\n--- RID: {rid} ---")
    evs = events_by_rid[rid]
    evs.sort(key=lambda x: x[0])
    for ts, fp, etype, rec in evs:
        # Just print summary
        status = rec.get('status') or rec.get('event') or rec.get('action') or ''
        reason = rec.get('reason') or rec.get('reject_reason') or ''
        print(f"  {ts} [{fp.split('/')[-1]}] {etype} | status={status} reason={reason}")
        if 'error' in rec:
            print(f"    error: {rec['error']}")
