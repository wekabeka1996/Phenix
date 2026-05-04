#!/usr/bin/env python3
"""Phase 3: fully-fresh suppressed rows and peak_giveback_state analysis."""
import json

LOGFILE = 'logs/trade_lifecycle.jsonl'
suppressed = []
with open(LOGFILE, encoding='utf-8', errors='replace') as f:
    for lineno, line in enumerate(f, 1):
        if 'POSITION_POLICY_SIDECAR_SUPPRESSED' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        suppressed.append((lineno, obj))

# Fully fresh rows
fully_fresh = []
for ln, o in suppressed:
    fs = o.get('freshness_snapshot', {})
    if all([fs.get('portfolio_fresh'), fs.get('features_fresh'), fs.get('regime_fresh'), fs.get('order_state_fresh')]):
        fully_fresh.append((ln, o))

print("Fully fresh suppressed rows:", len(fully_fresh))
for ln, o in fully_fresh[:12]:
    ps = o.get('position_snapshot', {})
    pg = o.get('peak_giveback_state', o.get('peak_giveback', {}))
    print("  line=" + str(ln) + " ts=" + str(o.get('ts_ms')) + " sym=" +
          str(o.get('symbol')) + " reasons=" + str(o.get('reason_codes')))
    print("    manage_state=" + str(ps.get('manage_state')) + " closing=" + str(ps.get('closing_position')
                                                                                ) + " portfolio_symbol_present=" + str(ps.get('portfolio_symbol_present')))
    print("    peak_giveback_state=" + str(pg))
    print("    trigger=" + str(o.get('trigger_event')))

# Check ALL suppressed rows for peak_giveback field
pg_keys = set()
for _, o in suppressed[:1000]:
    for k in o.keys():
        if 'peak' in k.lower() or 'giveback' in k.lower():
            pg_keys.add(k)
print("\nPeak/giveback keys in suppressed rows:", pg_keys)

# Find rows with BRACKETS_PENDING - extract full payload of 3
print("\n=== BRACKETS_PENDING suppressed rows (full payload, 3 samples) ===")
cnt = 0
for ln, o in suppressed:
    ps = o.get('position_snapshot', {})
    if ps.get('manage_state') == 'BRACKETS_PENDING':
        print("-- line=" + str(ln) + " --")
        print(json.dumps(o, indent=2)[:1500])
        cnt += 1
        if cnt >= 3:
            break

# Check if there are any rows with manage_state != None and no_active_lifecycle NOT in reason_codes
print("\n=== Rows with manage_state non-null and no_active_lifecycle NOT in reasons ===")
cnt2 = 0
for ln, o in suppressed:
    ps = o.get('position_snapshot', {})
    ms = ps.get('manage_state')
    rc = o.get('reason_codes', [])
    if ms is not None and 'no_active_lifecycle' not in rc:
        print("  line=" + str(ln) + " sym=" + str(o.get('symbol')) +
              " manage_state=" + str(ms) + " reasons=" + str(rc))
        cnt2 += 1
        if cnt2 >= 20:
            break
print("Total shown:", cnt2)

# Time span of the file
all_ts = [o.get('ts_ms', 0) for _, o in suppressed]
print("\nSuppressed ts range: min=" +
      str(min(all_ts)) + " max=" + str(max(all_ts)))
print("Duration ms:", max(all_ts) - min(all_ts))
print("Duration hours:", round((max(all_ts) - min(all_ts)) / 3600000, 2))
