#!/usr/bin/env python
"""Frozen snapshot census audit for trade_lifecycle.jsonl"""

import json
from pathlib import Path
from collections import defaultdict, Counter

frozen_path = Path('logs/trade_lifecycle.snapshot.20260505_203024.jsonl')

print("=" * 80)
print("STAGE C — FROZEN SNAPSHOT CENSUS")
print("=" * 80)
print(f"\nFrozen file: {frozen_path}")
print(f"Beginning exact event family count...\n")

# Exact event family census
event_families = {
    'POSITION_POLICY_SIDECAR_MODE_ACTIVE': [],
    'POSITION_POLICY_SIDECAR_SUPPRESSED': [],
    'POSITION_POLICY_SIDECAR_EVALUATED': [],
    'POSITION_POLICY_SIDECAR_SCORES': [],
    'POSITION_POLICY_SIDECAR_RECOMMENDED': [],
    'POSITION_POLICY_SIDECAR_ACTION_SKIPPED': [],
}

close_tokens = [
    'CLOSE_REQUESTED',
    'CLOSE_REQUEST_STATE',
    'CMD:CLOSE',
    'DEC:CLOSE',
    'EXECUTION_CLOSE_RECONCILED',
]

suppression_reasons = defaultdict(list)
all_symbols = Counter()
malformed_lines = []
raw_evidence = {
    'POSITION_POLICY_SIDECAR_MODE_ACTIVE': [],
    'POSITION_POLICY_SIDECAR_SUPPRESSED_first': None,
    'POSITION_POLICY_SIDECAR_SUPPRESSED_last': None,
    'POSITION_POLICY_SIDECAR_EVALUATED_first': None,
    'POSITION_POLICY_SIDECAR_SCORES_first': None,
    'POSITION_POLICY_SIDECAR_RECOMMENDED_first': None,
    'POSITION_POLICY_SIDECAR_ACTION_SKIPPED_first': None,
}

with frozen_path.open('r', encoding='utf-8', errors='ignore') as f:
    for line_num, line in enumerate(f, 1):
        if not line.strip():
            continue

        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            malformed_lines.append((line_num, line[:100]))
            continue

        # Extract common fields
        event_type = str(obj.get('event_type') or obj.get('event') or '')
        symbol = obj.get('symbol') or obj.get('payload', {}).get('symbol')
        ts_ms = obj.get('ts_ms') or obj.get(
            'timestamp_ms') or obj.get('timestamp')

        if symbol:
            all_symbols[str(symbol).upper()] += 1

        # Check each event family
        for fam, records in event_families.items():
            if fam in event_type:
                rec = {
                    'line': line_num,
                    'event_type': event_type,
                    'ts_ms': ts_ms,
                    'symbol': symbol,
                    'raw': line[:200],
                }
                records.append(rec)
                # Store raw evidence
                if fam == 'POSITION_POLICY_SIDECAR_MODE_ACTIVE':
                    raw_evidence[fam].append((line_num, obj))
                elif fam == 'POSITION_POLICY_SIDECAR_SUPPRESSED' and raw_evidence['POSITION_POLICY_SIDECAR_SUPPRESSED_first'] is None:
                    raw_evidence['POSITION_POLICY_SIDECAR_SUPPRESSED_first'] = (
                        line_num, obj)
                elif fam == 'POSITION_POLICY_SIDECAR_SUPPRESSED':
                    raw_evidence['POSITION_POLICY_SIDECAR_SUPPRESSED_last'] = (
                        line_num, obj)
                elif fam == 'POSITION_POLICY_SIDECAR_EVALUATED' and raw_evidence['POSITION_POLICY_SIDECAR_EVALUATED_first'] is None:
                    raw_evidence['POSITION_POLICY_SIDECAR_EVALUATED_first'] = (
                        line_num, obj)
                elif fam == 'POSITION_POLICY_SIDECAR_SCORES' and raw_evidence['POSITION_POLICY_SIDECAR_SCORES_first'] is None:
                    raw_evidence['POSITION_POLICY_SIDECAR_SCORES_first'] = (
                        line_num, obj)
                elif fam == 'POSITION_POLICY_SIDECAR_RECOMMENDED' and raw_evidence['POSITION_POLICY_SIDECAR_RECOMMENDED_first'] is None:
                    raw_evidence['POSITION_POLICY_SIDECAR_RECOMMENDED_first'] = (
                        line_num, obj)
                elif fam == 'POSITION_POLICY_SIDECAR_ACTION_SKIPPED' and raw_evidence['POSITION_POLICY_SIDECAR_ACTION_SKIPPED_first'] is None:
                    raw_evidence['POSITION_POLICY_SIDECAR_ACTION_SKIPPED_first'] = (
                        line_num, obj)

        # Check for suppression reasons
        if 'SIDECAR_SUPPRESSED' in event_type:
            reason = obj.get('reason') or obj.get(
                'suppression_reason') or obj.get('payload', {}).get('reason')
            if reason:
                suppression_reasons[str(reason)].append({
                    'line': line_num,
                    'ts_ms': ts_ms,
                    'symbol': symbol,
                })

# Print event census
print("=" * 80)
print("TABLE C — FROZEN SIDECAR EVENT CENSUS")
print("=" * 80)

for fam in ['POSITION_POLICY_SIDECAR_MODE_ACTIVE', 'POSITION_POLICY_SIDECAR_SUPPRESSED',
            'POSITION_POLICY_SIDECAR_EVALUATED', 'POSITION_POLICY_SIDECAR_SCORES',
            'POSITION_POLICY_SIDECAR_RECOMMENDED', 'POSITION_POLICY_SIDECAR_ACTION_SKIPPED']:
    records = event_families[fam]
    count = len(records)
    if count == 0:
        print(f"\n{fam}: 0 occurrences")
    else:
        first = records[0]
        last = records[-1]
        print(f"\n{fam}:")
        print(f"  exact_count: {count}")
        print(f"  first_line: {first['line']}")
        print(f"  first_ts_ms: {first['ts_ms']}")
        print(f"  last_line: {last['line']}")
        print(f"  last_ts_ms: {last['ts_ms']}")

# Print suppression reason census
print("\n" + "=" * 80)
print("TABLE D — FROZEN SUPPRESSION REASON CENSUS")
print("=" * 80)

if suppression_reasons:
    for reason, records in sorted(suppression_reasons.items(), key=lambda x: -len(x[1])):
        count = len(records)
        first = records[0]
        last = records[-1]
        symbols = set(str(r['symbol']).upper() for r in records if r['symbol'])
        print(f"\n{reason}:")
        print(f"  exact_count: {count}")
        print(f"  first_line: {first['line']}")
        print(f"  first_ts_ms: {first['ts_ms']}")
        print(f"  last_line: {last['line']}")
        print(f"  last_ts_ms: {last['ts_ms']}")
        print(f"  symbols_seen: {sorted(symbols)}")
else:
    print("No suppression reasons found.")

# Malformed line report
print("\n" + "=" * 80)
print("MALFORMED LINES IN FROZEN SNAPSHOT")
print("=" * 80)
print(f"Total malformed: {len(malformed_lines)}")
if malformed_lines:
    for ln, content in malformed_lines[:5]:
        print(f"  line {ln}: {content}...")

print("\n" + "=" * 80)
print("SYMBOLS SEEN IN FROZEN SNAPSHOT")
print("=" * 80)
for sym, count in sorted(all_symbols.items(), key=lambda x: -x[1]):
    print(f"  {sym}: {count} rows")

# Save raw evidence
print("\n" + "=" * 80)
print("RAW EVIDENCE EXTRACTION")
print("=" * 80)

if raw_evidence['POSITION_POLICY_SIDECAR_MODE_ACTIVE']:
    print("\nAll POSITION_POLICY_SIDECAR_MODE_ACTIVE rows:")
    for ln, obj in raw_evidence['POSITION_POLICY_SIDECAR_MODE_ACTIVE'][:10]:
        print(f"  line {ln}: {json.dumps(obj, ensure_ascii=False)[:150]}...")

if raw_evidence['POSITION_POLICY_SIDECAR_SUPPRESSED_first']:
    ln, obj = raw_evidence['POSITION_POLICY_SIDECAR_SUPPRESSED_first']
    print(f"\nFirst POSITION_POLICY_SIDECAR_SUPPRESSED row (line {ln}):")
    print(f"  {json.dumps(obj, ensure_ascii=False)[:300]}...")

if raw_evidence['POSITION_POLICY_SIDECAR_SUPPRESSED_last']:
    ln, obj = raw_evidence['POSITION_POLICY_SIDECAR_SUPPRESSED_last']
    print(f"\nLast POSITION_POLICY_SIDECAR_SUPPRESSED row (line {ln}):")
    print(f"  {json.dumps(obj, ensure_ascii=False)[:300]}...")

print("\n" + "=" * 80)
print("CENSUS COMPLETE")
print("=" * 80)
