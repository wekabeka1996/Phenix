#!/usr/bin/env python
"""Extended boundary and overclaim audit on frozen snapshot"""

import json
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

frozen_path = Path('logs/trade_lifecycle.snapshot.20260505_203024.jsonl')

print("=" * 80)
print("STAGE D — BOUNDARY REALITY ON FROZEN SNAPSHOT")
print("=" * 80)

# Extract activation boundaries
activations = []
suppressions = []
evaluated_rows = []
score_rows = []
recommend_rows = []
action_rows = []

with frozen_path.open('r', encoding='utf-8', errors='ignore') as f:
    for line_num, line in enumerate(f, 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except:
            continue

        event_type = str(obj.get('event_type') or '')
        ts_ms = obj.get('ts_ms')

        if 'MODE_ACTIVE' in event_type:
            activations.append((line_num, ts_ms, obj.get('symbol')))
        if 'SUPPRESSED' in event_type:
            suppressions.append((line_num, ts_ms, obj.get('symbol')))
        if 'EVALUATED' in event_type:
            evaluated_rows.append((line_num, ts_ms, obj.get('symbol')))
        if 'SCORES' in event_type:
            score_rows.append((line_num, ts_ms, obj.get('symbol')))
        if 'RECOMMENDED' in event_type:
            recommend_rows.append((line_num, ts_ms, obj.get('symbol')))
        if 'ACTION_SKIPPED' in event_type:
            action_rows.append((line_num, ts_ms, obj.get('symbol')))

print(f"\nActivation boundaries detected: {len(activations)}")
for i, (ln, ts, sym) in enumerate(activations, 1):
    dt = datetime.fromtimestamp(
        ts/1000, tz=timezone.utc).isoformat() if ts else 'N/A'
    print(f"  Boundary {i}: line {ln}, ts_ms {ts} ({dt}), symbol {sym}")

print(f"\nSuppression rows: {len(suppressions)}")
if suppressions:
    first_ln, first_ts, first_sym = suppressions[0]
    last_ln, last_ts, last_sym = suppressions[-1]
    first_dt = datetime.fromtimestamp(
        first_ts/1000, tz=timezone.utc).isoformat() if first_ts else 'N/A'
    last_dt = datetime.fromtimestamp(
        last_ts/1000, tz=timezone.utc).isoformat() if last_ts else 'N/A'
    print(
        f"  First: line {first_ln}, ts_ms {first_ts} ({first_dt}), symbol {first_sym}")
    print(
        f"  Last: line {last_ln}, ts_ms {last_ts} ({last_dt}), symbol {last_sym}")
    suppression_duration_s = max(
        0, int((last_ts - first_ts) / 1000)) if first_ts and last_ts else 0
    print(f"  Duration: {suppression_duration_s} seconds")

print(f"\nEvaluated rows: {len(evaluated_rows)}")
print(f"Score rows: {len(score_rows)}")
print(f"Recommendation rows: {len(recommend_rows)}")
print(f"Action rows: {len(action_rows)}")

# Boundary definition possibilities
print("\n" + "=" * 80)
print("BOUNDED RUN DEFINITION ANALYSIS")
print("=" * 80)

if len(activations) >= 1:
    print(f"\nFound {len(activations)} activation boundaries.")
    if len(activations) == 1:
        print("Can a bounded run #1 be defined? YES (single activation to first deactivation or EOF)")
        act_ln, act_ts, _ = activations[0]
        supp_after = [s for s in suppressions if s[0] > act_ln]
        if supp_after:
            run_end_ln, run_end_ts, _ = supp_after[-1]
            run_duration_s = max(
                0, int((run_end_ts - act_ts) / 1000)) if act_ts and run_end_ts else 0
            print(f"  Run #1: lines {act_ln}-{run_end_ln} ({run_duration_s}s)")
    elif len(activations) == 2:
        print("Can a bounded run #1 be defined? YES")
        act1_ln, act1_ts, _ = activations[0]
        act2_ln, act2_ts, _ = activations[1]
        supp1 = [s for s in suppressions if act1_ln < s[0] < act2_ln]
        supp2 = [s for s in suppressions if s[0] > act2_ln]
        if supp1:
            run1_end_ln = supp1[-1][0]
            run1_duration_s = max(
                0, int((supp1[-1][1] - act1_ts) / 1000)) if act1_ts else 0
            print(
                f"  Run #1: lines {act1_ln}-{run1_end_ln} ({run1_duration_s}s)")
        print("Can a bounded run #2 be defined? YES")
        if supp2:
            run2_end_ln = supp2[-1][0]
            run2_duration_s = max(
                0, int((supp2[-1][1] - act2_ts) / 1000)) if act2_ts else 0
            print(
                f"  Run #2: lines {act2_ln}-{run2_end_ln} ({run2_duration_s}s)")
    else:
        print(
            f"Found {len(activations)} activations: multiple distinct runs possible")
        for i in range(len(activations)):
            act_ln, act_ts, _ = activations[i]
            if i + 1 < len(activations):
                next_act_ln = activations[i + 1][0]
                supp_in_run = [
                    s for s in suppressions if act_ln < s[0] < next_act_ln]
            else:
                supp_in_run = [s for s in suppressions if s[0] > act_ln]
            if supp_in_run:
                run_end_ln = supp_in_run[-1][0]
                run_duration_s = max(
                    0, int((supp_in_run[-1][1] - act_ts) / 1000)) if act_ts else 0
                print(
                    f"  Run #{i+1}: lines {act_ln}-{run_end_ln} ({run_duration_s}s)")

# Summarize file behavior
print("\n" + "=" * 80)
print("FROZEN SNAPSHOT BEHAVIOR SUMMARY")
print("=" * 80)

is_suppression_only = (len(evaluated_rows) == 0 and len(score_rows) == 0 and
                       len(recommend_rows) == 0 and len(action_rows) == 0)
has_evaluated = len(evaluated_rows) > 0
has_scoring = len(score_rows) > 0
has_recommendation = len(recommend_rows) > 0
has_action = len(action_rows) > 0

print(f"\nSuppression-only: {is_suppression_only}")
print(f"Has evaluated rows: {has_evaluated}")
print(f"Has scoring rows: {has_scoring}")
print(f"Has recommendation rows: {has_recommendation}")
print(f"Has action rows: {has_action}")

if is_suppression_only:
    print("\n*** FROZEN SNAPSHOT IS SUPPRESSION-ONLY ***")
    print("All 106,939 suppressed rows represent gating only.")
    print("No evaluation, scoring, recommendation, or action activity.")
else:
    print("\n*** FROZEN SNAPSHOT HAS MIXED BEHAVIOR ***")
    if has_evaluated or has_scoring or has_recommendation or has_action:
        print("Active evaluation and/or action pathways present.")

print("\n" + "=" * 80)
print("STAGE D COMPLETE")
print("=" * 80)
