#!/usr/bin/env python
"""Overclaim audit against frozen snapshot"""

import json
from pathlib import Path

frozen_path = Path('logs/trade_lifecycle.snapshot.20260505_203024.jsonl')

print("=" * 80)
print("OVERCLAIM AUDIT AGAINST FROZEN SNAPSHOT")
print("=" * 80)

# Count exact event families from frozen file
exact_counts = {
    'MODE_ACTIVE': 0,
    'SUPPRESSED': 0,
    'EVALUATED': 0,
    'SCORES': 0,
    'RECOMMENDED': 0,
    'ACTION_SKIPPED': 0,
}

with frozen_path.open('r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except:
            continue
        event_type = str(obj.get('event_type') or '')
        if 'MODE_ACTIVE' in event_type:
            exact_counts['MODE_ACTIVE'] += 1
        if 'SUPPRESSED' in event_type:
            exact_counts['SUPPRESSED'] += 1
        if 'EVALUATED' in event_type:
            exact_counts['EVALUATED'] += 1
        if 'SCORES' in event_type:
            exact_counts['SCORES'] += 1
        if 'RECOMMENDED' in event_type:
            exact_counts['RECOMMENDED'] += 1
        if 'ACTION_SKIPPED' in event_type:
            exact_counts['ACTION_SKIPPED'] += 1

# Statements to audit
statements = {
    1: ("The file has exactly one activation row.", exact_counts['MODE_ACTIVE'] == 1),
    2: ("The file has more than one activation row.", exact_counts['MODE_ACTIVE'] > 1),
    3: ("The file is globally suppression-only.",
        exact_counts['SUPPRESSED'] > 0 and exact_counts['EVALUATED'] == 0 and
        exact_counts['SCORES'] == 0 and exact_counts['RECOMMENDED'] == 0 and
        exact_counts['ACTION_SKIPPED'] == 0),
    4: ("The file contains evaluated rows.", exact_counts['EVALUATED'] > 0),
    5: ("The file contains score rows.", exact_counts['SCORES'] > 0),
    6: ("The file contains recommendation rows.", exact_counts['RECOMMENDED'] > 0),
    7: ("A bounded run #1 can be formed.", exact_counts['MODE_ACTIVE'] >= 1),
    8: ("A bounded run #2 can be formed.", exact_counts['MODE_ACTIVE'] >= 2),
}

for stmt_id, (claim, result) in statements.items():
    if result == True:
        verdict = "SUPPORTED"
    elif result == False:
        verdict = "UNSUPPORTED" if not "suppression-only" in claim.lower() else "CONTRADICTED_BY_FROZEN_SNAPSHOT"

    print(f"\nStatement {stmt_id}: {claim}")
    print(f"  Verdict: {verdict}")
    print(f"  Evidence: ", end="")

    if stmt_id == 1:
        print(f"MODE_ACTIVE count = {exact_counts['MODE_ACTIVE']} (expect 1)")
    elif stmt_id == 2:
        print(
            f"MODE_ACTIVE count = {exact_counts['MODE_ACTIVE']} (expect > 1)")
    elif stmt_id == 3:
        print(f"SUPPRESSED={exact_counts['SUPPRESSED']}, EVALUATED={exact_counts['EVALUATED']}, SCORES={exact_counts['SCORES']}, RECOMMENDED={exact_counts['RECOMMENDED']}, ACTION={exact_counts['ACTION_SKIPPED']}")
    elif stmt_id == 4:
        print(f"EVALUATED count = {exact_counts['EVALUATED']} (expect > 0)")
    elif stmt_id == 5:
        print(f"SCORES count = {exact_counts['SCORES']} (expect > 0)")
    elif stmt_id == 6:
        print(
            f"RECOMMENDED count = {exact_counts['RECOMMENDED']} (expect > 0)")
    elif stmt_id == 7:
        print(f"MODE_ACTIVE count = {exact_counts['MODE_ACTIVE']} (need >= 1)")
    elif stmt_id == 8:
        print(f"MODE_ACTIVE count = {exact_counts['MODE_ACTIVE']} (need >= 2)")

print("\n" + "=" * 80)
print("OVERCLAIM AUDIT COMPLETE")
print("=" * 80)
